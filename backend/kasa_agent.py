import asyncio
import socket
import struct
import re
import subprocess
import platform
from typing import List, Dict, Optional, Any
from kasa import Discover, SmartDevice, SmartBulb, SmartPlug

# Try importing optional discovery libraries
try:
    from zeroconf import ServiceBrowser, Zeroconf, ServiceListener
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False
    print("[KasaAgent] zeroconf not installed. mDNS discovery disabled. Install with: pip install zeroconf")

try:
    import netifaces
    HAS_NETIFACES = True
except ImportError:
    HAS_NETIFACES = False


class NetworkDeviceInfo:
    """Represents any discovered network device, not just Kasa."""
    def __init__(self, ip: str, mac: str = None, hostname: str = None, 
                 vendor: str = None, device_type: str = "unknown", 
                 open_ports: List[int] = None, source: str = "unknown"):
        self.ip = ip
        self.mac = mac
        self.hostname = hostname
        self.vendor = vendor
        self.device_type = device_type
        self.open_ports = open_ports or []
        self.source = source
    
    def to_dict(self) -> Dict:
        return {
            "ip": self.ip,
            "mac": self.mac,
            "hostname": self.hostname,
            "vendor": self.vendor,
            "device_type": self.device_type,
            "open_ports": self.open_ports,
            "source": self.source
        }


class KasaAgent:
    # MAC OUI vendor database (common smart home / IoT vendors)
    OUI_DATABASE = {
        # Amazon
        "B0:BE:76": "Amazon Echo/Alexa",
        "AC:63:BE": "Amazon Echo/Alexa",
        "A0:02:DC": "Amazon Fire TV",
        "34:D2:70": "Amazon Kindle/Fire",
        # Google
        "50:F5:DA": "Google Home/Chromecast",
        "18:B4:30": "Google Nest",
        "3C:5A:B4": "Google Nest Hub",
        "94:EB:2C": "Google Home Mini",
        "A4:77:33": "Google Chromecast",
        "6C:29:95": "Google Pixel/Device",
        # Apple
        "C0:49:EF": "Apple iPhone/iPad",
        "F0:18:98": "Apple Device",
        "8C:85:90": "Apple Device",
        # Samsung
        "00:12:EE": "Samsung SmartTV",
        "04:66:65": "Samsung Galaxy",
        "D0:DF:B2": "Samsung TV",
        "8C:3A:51": "Samsung TV",
        # TP-Link / Kasa
        "C0:06:C3": "TP-Link Kasa",
        "50:C7:BF": "TP-Link Smart Device",
        "B0:4E:26": "TP-Link Router/Switch",
        "00:0A:EB": "TP-Link Device",
        # Philips
        "00:17:88": "Philips Hue Bridge",
        "30:8C:FB": "Philips Hue Light",
        # Sonos
        "64:16:66": "Sonos Speaker",
        "48:A6:B8": "Sonos Speaker",
        "78:28:CA": "Sonos Speaker",
        # Ring
        "00:0E:58": "Ring Doorbell/Camera",
        "B8:5A:F7": "Ring Chime",
        # Roku
        "B0:A7:37": "Roku Streaming",
        "00:0D:4B": "Roku Device",
        "CC:6D:A0": "Roku Express",
        # LG
        "A8:23:FE": "LG SmartTV",
        "C8:08:6A": "LG Device",
        # Sony
        "00:04:1E": "Sony TV/PlayStation",
        "7C:84:B6": "Sony TV",
        # Microsoft
        "00:15:5D": "Xbox",
        "28:18:78": "Xbox One",
        # Nintendo
        "00:1E:A9": "Nintendo Wii",
        "8C:CD:E8": "Nintendo Switch",
        "B8:8A:EC": "Nintendo 3DS",
        # Wyze
        "2C:AA:8E": "Wyze Camera",
        # Ecobee
        "44:61:32": "Ecobee Thermostat",
        # Lutron
        "00:0F:FE": "Lutron Caseta",
        # Belkin/Wemo
        "B4:75:0E": "Belkin Wemo",
        "EC:1A:59": "Belkin Wemo Insight",
    }

    COMMON_IOT_PORTS = {
        80: "HTTP",
        443: "HTTPS",
        8080: "HTTP-Alt",
        8008: "Chromecast",
        8009: "Chromecast",
        8443: "HTTPS-Alt",
        554: "RTSP (Camera)",
        1900: "UPnP/SSDP",
        5353: "mDNS",
        5000: "UPnP",
        6666: "TP-Link Kasa",
        6667: "TP-Link Kasa",
        9999: "TP-Link Kasa (old)",
        7000: "AirPlay",
        7100: "AirPlay",
        8000: "Sonos/Streaming",
        3400: "Sonos",
        3401: "Sonos",
        8883: "MQTT",
        1883: "MQTT-alt",
        5683: "CoAP",
        49152: "UPnP",
        49153: "UPnP",
        49154: "UPnP",
    }

    def __init__(self, known_devices=None):
        self.devices = {}  # Kasa devices (ip -> SmartDevice)
        self.network_devices = []  # All network devices
        self.known_devices_config = known_devices or []

    async def initialize(self):
        """Initializes devices from the saved configuration."""
        if self.known_devices_config:
            print(f"[KasaAgent] Initializing {len(self.known_devices_config)} known devices...")
            tasks = []
            for d in self.known_devices_config:
                if not d: continue
                ip = d.get('ip')
                alias = d.get('alias')
                if ip:
                    tasks.append(self._add_known_device(ip, alias, d))
            
            if tasks:
                await asyncio.gather(*tasks)

    async def _add_known_device(self, ip, alias, info):
        """Adds a device from settings without discovery scan."""
        try:
            dev = await Discover.discover_single(ip)
            if dev:
                await dev.update()
                self.devices[ip] = dev
                print(f"[KasaAgent] Loaded known device: {dev.alias} ({ip})")
            else:
                print(f"[KasaAgent] Could not connect to known device at {ip}")
                # Keep it as a network device anyway
                self.network_devices.append(NetworkDeviceInfo(
                    ip=ip, hostname=alias, source="known_offline"
                ))
        except Exception as e:
            print(f"[KasaAgent] Error loading known device {ip}: {e}")
            self.network_devices.append(NetworkDeviceInfo(
                ip=ip, hostname=alias, source="known_error"
            ))

    async def discover_devices(self):
        """Discovers Kasa devices on the local network."""
        print("Discovering Kasa devices (Broadcast)...")
        found_devices = await Discover.discover(target="255.255.255.255", timeout=5)
        print(f"[KasaAgent] Raw discovery found {len(found_devices)} devices.")
        
        for ip, dev in found_devices.items():
            await dev.update()
            self.devices[ip] = dev
            
        device_list = []
        for ip, dev in self.devices.items():
            dev_type = "unknown"
            if dev.is_bulb:
                dev_type = "bulb"
            elif dev.is_plug:
                dev_type = "plug"
            elif dev.is_strip:
                dev_type = "strip"
            elif dev.is_dimmer:
                dev_type = "dimmer"

            device_list.append({
                "ip": ip,
                "alias": dev.alias,
                "model": dev.model,
                "type": dev_type,
                "is_on": dev.is_on,
                "brightness": dev.brightness if dev.is_bulb or dev.is_dimmer else None,
                "hsv": dev.hsv if dev.is_bulb and dev.is_color else None,
                "has_color": dev.is_color if dev.is_bulb else False,
                "has_brightness": dev.is_dimmable if dev.is_bulb or dev.is_dimmer else False
            })
            
        print(f"Total Kasa devices (found + cached): {len(device_list)}")
        return device_list

    async def scan_full_network(self) -> List[Dict]:
        """
        Full network scan - discovers ALL devices, not just Kasa.
        Uses ARP, UPnP, mDNS, and port scanning.
        """
        print("[KasaAgent] 🔍 Starting full network scan...")
        all_devices = []
        
        # Method 1: ARP scan (fastest)
        print("[KasaAgent]   📡 ARP scan...")
        arp_devices = await self._arp_scan()
        all_devices.extend(arp_devices)
        
        # Method 2: UPnP/SSDP discovery
        print("[KasaAgent]   📡 UPnP/SSDP discovery...")
        upnp_devices = await self._upnp_discover()
        all_devices.extend(upnp_devices)
        
        # Method 3: mDNS/Bonjour discovery
        if HAS_ZEROCONF:
            print("[KasaAgent]   📡 mDNS discovery...")
            mdns_devices = await self._mdns_discover()
            all_devices.extend(mdns_devices)
        
        # Method 4: Quick port scan on discovered IPs
        print("[KasaAgent]   📡 Port scanning discovered devices...")
        for device in all_devices:
            device.open_ports = await self._quick_port_scan(device.ip)
            # Update device type based on ports
            device.device_type = self._identify_device_type(device)
        
        # Deduplicate by IP
        self.network_devices = self._deduplicate_devices(all_devices)
        
        result = [d.to_dict() for d in self.network_devices]
        print(f"[KasaAgent] 🔍 Network scan complete: {len(result)} devices found")
        
        # Print summary
        device_types = {}
        for d in self.network_devices:
            device_types[d.device_type] = device_types.get(d.device_type, 0) + 1
        
        for dtype, count in device_types.items():
            print(f"[KasaAgent]     {dtype}: {count}")
        
        return result

    async def _arp_scan(self) -> List[NetworkDeviceInfo]:
        """Scan local network using ARP table and ping sweep."""
        devices = []
        
        # Method 1a: Check ARP table (instant)
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5)
            else:
                result = subprocess.run(["arp", "-n"], capture_output=True, text=True, timeout=5)
            
            for line in result.stdout.split("\n"):
                # Windows: "192.168.1.5     xx-xx-xx-xx-xx-xx     dynamic"
                # Linux: "192.168.1.5     ether   xx:xx:xx:xx:xx:xx   C   eth0"
                match_ip = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                match_mac = re.search(r'([0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2}[-:][0-9A-Fa-f]{2})', line)
                
                if match_ip:
                    ip = match_ip.group(1)
                    mac = match_mac.group(1).replace("-", ":").upper() if match_mac else None
                    
                    # Skip broadcast and multicast
                    if ip.endswith(".255") or ip.endswith(".0") or ip == "255.255.255.255":
                        continue
                    
                    vendor = self._lookup_mac_vendor(mac) if mac else None
                    
                    devices.append(NetworkDeviceInfo(
                        ip=ip, mac=mac, vendor=vendor, source="arp"
                    ))
        except Exception as e:
            print(f"[KasaAgent] ARP table read failed: {e}")
        
        # Method 1b: Try to resolve hostnames
        for device in devices:
            try:
                hostname = socket.gethostbyaddr(device.ip)[0]
                device.hostname = hostname
            except:
                pass
        
        return devices

    async def _upnp_discover(self) -> List[NetworkDeviceInfo]:
        """Discover devices via UPnP/SSDP."""
        devices = []
        
        # Search targets for different device types
        search_targets = [
            "ssdp:all",
            "urn:schemas-upnp-org:device:MediaRenderer:1",  # Smart TVs, speakers
            "urn:schemas-upnp-org:device:MediaServer:1",     # Media servers
            "urn:schemas-upnp-org:device:InternetGatewayDevice:1",  # Routers
            "urn:schemas-upnp-org:device:WANDevice:1",
            "urn:dial-multiscreen-org:service:dial:1",  # Chromecast
            "urn:schemas-upnp-org:device:Basic:1",       # Basic devices
        ]
        
        for st in search_targets:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.settimeout(3)
                
                msg = (
                    'M-SEARCH * HTTP/1.1\r\n'
                    f'HOST: 239.255.255.250:1900\r\n'
                    'MAN: "ssdp:discover"\r\n'
                    f'MX: 3\r\n'
                    f'ST: {st}\r\n'
                    '\r\n'
                )
                
                sock.sendto(msg.encode(), ('239.255.255.250', 1900))
                
                try:
                    while True:
                        data, addr = sock.recvfrom(4096)
                        response = data.decode('utf-8', errors='ignore')
                        
                        # Parse location and server info
                        location = re.search(r'LOCATION:\s*(\S+)', response)
                        server = re.search(r'SERVER:\s*(.+?)(?:\r|\n|$)', response)
                        usn = re.search(r'USN:\s*(\S+)', response)
                        
                        device_info = NetworkDeviceInfo(
                            ip=addr[0],
                            source="upnp",
                            device_type=self._classify_upnp_device(response, usn.group(1) if usn else "")
                        )
                        
                        if server:
                            device_info.hostname = server.group(1)[:100]
                        
                        if not any(d.ip == addr[0] for d in devices):
                            devices.append(device_info)
                            
                except socket.timeout:
                    pass
                finally:
                    sock.close()
                    
            except Exception as e:
                pass
        
        return devices

    async def _mdns_discover(self) -> List[NetworkDeviceInfo]:
        """Discover devices via mDNS/Bonjour."""
        devices = []
        
        if not HAS_ZEROCONF:
            return devices
        
        discovery_done = asyncio.Event()
        discovered = []
        
        class MDNSListener(ServiceListener):
            def add_service(self, zeroconf, type, name):
                info = zeroconf.get_service_info(type, name)
                if info and info.addresses:
                    for addr in info.addresses:
                        ip = socket.inet_ntoa(addr)
                        device = NetworkDeviceInfo(
                            ip=ip,
                            hostname=info.server,
                            source="mdns",
                            device_type=type.split("._")[1].split(".")[0] if "._" in type else type
                        )
                        # Extract port info
                        if info.port:
                            device.open_ports = [info.port]
                        discovered.append(device)
            
            def remove_service(self, zeroconf, type, name):
                pass
            
            def update_service(self, zeroconf, type, name):
                pass
        
        # Common mDNS service types
        service_types = [
            "_http._tcp.local.",
            "_https._tcp.local.",
            "_googlecast._tcp.local.",       # Chromecast
            "_airplay._tcp.local.",          # AirPlay
            "_raop._tcp.local.",             # AirPlay audio
            "_hap._tcp.local.",              # HomeKit
            "_printer._tcp.local.",          # Printers
            "_ipp._tcp.local.",              # IPP Printers
            "_smb._tcp.local.",              # Samba/Windows
            "_daap._tcp.local.",             # iTunes
            "_ssh._tcp.local.",              # SSH
            "_ftp._tcp.local.",              # FTP
            "_nfs._tcp.local.",              # NFS
            "_spotify-connect._tcp.local.",  # Spotify
            "_dlna._tcp.local.",             # DLNA
        ]
        
        try:
            zeroconf = Zeroconf()
            listener = MDNSListener()
            
            browsers = []
            for st in service_types:
                browser = ServiceBrowser(zeroconf, st, listener)
                browsers.append(browser)
            
            # Wait for services to be discovered
            await asyncio.sleep(3)
            zeroconf.close()
            
        except Exception as e:
            print(f"[KasaAgent] mDNS discovery failed: {e}")
        
        devices.extend(discovered)
        return devices

    async def _quick_port_scan(self, ip: str) -> List[int]:
        """Quickly scan common ports on a device."""
        open_ports = []
        
        for port in [80, 443, 8080, 8008, 8009, 8443, 554, 1900, 5353, 
                      5000, 6666, 6667, 9999, 7000, 8000, 8883]:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(ip, port),
                    timeout=0.5
                )
                open_ports.append(port)
                writer.close()
                await writer.wait_closed()
            except:
                pass
        
        return open_ports

    def _lookup_mac_vendor(self, mac: str) -> Optional[str]:
        """Lookup MAC vendor from OUI database."""
        if not mac:
            return None
        mac_upper = mac.upper().replace(":", "-")[:8]
        return self.OUI_DATABASE.get(mac_upper, None)

    def _classify_upnp_device(self, response: str, usn: str) -> str:
        """Classify a device from its UPnP response."""
        response_lower = response.lower()
        usn_lower = usn.lower()
        
        if "chromecast" in response_lower or "google" in response_lower:
            return "chromecast"
        if "roku" in response_lower:
            return "roku"
        if "smart tv" in response_lower or "television" in response_lower:
            return "smart_tv"
        if "sonos" in response_lower:
            return "sonos_speaker"
        if "mediaRenderer" in response_lower or "MediaRenderer" in response:
            return "media_renderer"
        if "mediaServer" in response_lower or "MediaServer" in response:
            return "media_server"
        if "internetgateway" in response_lower:
            return "router"
        if "printer" in response_lower:
            return "printer"
        if "camera" in response_lower:
            return "camera"
        return "upnp_device"

    def _identify_device_type(self, device: NetworkDeviceInfo) -> str:
        """Identify device type based on all available information."""
        # Already classified by UPnP/mDNS
        if device.device_type and device.device_type != "unknown":
            return device.device_type
        
        # Check vendor
        if device.vendor:
            vendor_lower = device.vendor.lower()
            if "amazon" in vendor_lower:
                return "amazon_device"
            if "google" in vendor_lower:
                return "google_device"
            if "apple" in vendor_lower:
                return "apple_device"
            if "samsung" in vendor_lower:
                return "samsung_device"
            if "lg" in vendor_lower:
                return "lg_device"
            if "sony" in vendor_lower:
                return "sony_device"
            if "philips" in vendor_lower:
                return "philips_hue"
            if "ring" in vendor_lower:
                return "ring_device"
            if "sonos" in vendor_lower:
                return "sonos_speaker"
            if "roku" in vendor_lower:
                return "roku_device"
            if "wyze" in vendor_lower:
                return "camera"
        
        # Check ports
        if 8008 in device.open_ports or 8009 in device.open_ports:
            return "chromecast"
        if 554 in device.open_ports:
            return "camera"
        if 7000 in device.open_ports:
            return "airplay_device"
        if 8883 in device.open_ports:
            return "iot_device"
        if 80 in device.open_ports or 443 in device.open_ports:
            return "web_device"
        
        # Check hostname
        if device.hostname:
            hostname_lower = device.hostname.lower()
            if "tv" in hostname_lower:
                return "smart_tv"
            if "phone" in hostname_lower or "iphone" in hostname_lower:
                return "phone"
            if "laptop" in hostname_lower or "desktop" in hostname_lower:
                return "computer"
            if "printer" in hostname_lower:
                return "printer"
        
        return "unknown_device"

    def _deduplicate_devices(self, devices: List[NetworkDeviceInfo]) -> List[NetworkDeviceInfo]:
        """Merge duplicate devices by IP, preferring more detailed entries."""
        device_map = {}
        
        for device in devices:
            if device.ip not in device_map:
                device_map[device.ip] = device
            else:
                existing = device_map[device.ip]
                # Merge: keep the entry with more information
                if device.mac and not existing.mac:
                    existing.mac = device.mac
                if device.hostname and not existing.hostname:
                    existing.hostname = device.hostname
                if device.vendor and not existing.vendor:
                    existing.vendor = device.vendor
                if device.device_type != "unknown" and existing.device_type == "unknown":
                    existing.device_type = device.device_type
                # Combine ports
                for port in device.open_ports:
                    if port not in existing.open_ports:
                        existing.open_ports.append(port)
                # Combine sources
                if device.source not in existing.source:
                    existing.source = f"{existing.source}+{device.source}"
        
        return list(device_map.values())

    def get_device_by_alias(self, alias):
        """Finds a Kasa device by its alias (case-insensitive)."""
        for ip, dev in self.devices.items():
            if dev.alias.lower() == alias.lower():
                return dev
        return None

    def _resolve_device(self, target):
        """Resolves a target string (IP or Alias) to a Kasa device object."""
        if target in self.devices:
            return self.devices[target]
        dev = self.get_device_by_alias(target)
        if dev:
            return dev
        return None

    def name_to_hsv(self, color_name):
        """Converts common color names to HSV."""
        color_name = color_name.lower().strip()
        colors = {
            "red": (0, 100, 100),
            "orange": (30, 100, 100),
            "yellow": (60, 100, 100),
            "green": (120, 100, 100),
            "cyan": (180, 100, 100),
            "blue": (240, 100, 100),
            "purple": (300, 100, 100),
            "pink": (300, 50, 100),
            "white": (0, 0, 100),
            "warm": (30, 20, 100),
            "cool": (200, 10, 100),
            "daylight": (0, 0, 100),
        }
        return colors.get(color_name, None)

    async def turn_on(self, target):
        """Turns on the Kasa device (Target: IP or Alias)."""
        dev = self._resolve_device(target)
        if dev:
            try:
                await dev.turn_on()
                await dev.update()
                return True
            except Exception as e:
                print(f"Error turning on {target}: {e}")
                return False
        if target.count(".") == 3:
            try:
                dev = await Discover.discover_single(target)
                if dev:
                    self.devices[target] = dev
                    await dev.turn_on()
                    await dev.update()
                    return True
            except Exception:
                pass
        return False

    async def turn_off(self, target):
        """Turns off the Kasa device (Target: IP or Alias)."""
        dev = self._resolve_device(target)
        if dev:
            try:
                await dev.turn_off()
                await dev.update()
                return True
            except Exception as e:
                print(f"Error turning off {target}: {e}")
                return False
        if target.count(".") == 3:
            try:
                dev = await Discover.discover_single(target)
                if dev:
                    self.devices[target] = dev
                    await dev.turn_off()
                    await dev.update()
                    return True
            except Exception:
                pass
        return False

    async def set_brightness(self, target, brightness):
        """Sets brightness (0-100)."""
        dev = self._resolve_device(target)
        if dev and (dev.is_dimmable or dev.is_bulb):
            try:
                await dev.set_brightness(int(brightness))
                await dev.update()
                return True
            except Exception as e:
                print(f"Error setting brightness for {target}: {e}")
        return False

    async def set_color(self, target, color_input):
        """Sets color by name or direct HSV tuple."""
        dev = self._resolve_device(target)
        if not dev or not dev.is_color:
            return False
        hsv = None
        if isinstance(color_input, str):
            hsv = self.name_to_hsv(color_input)
        elif isinstance(color_input, (tuple, list)) and len(color_input) == 3:
            hsv = color_input
        if hsv:
            try:
                await dev.set_hsv(int(hsv[0]), int(hsv[1]), int(hsv[2]))
                await dev.update()
                return True
            except Exception as e:
                print(f"Error setting color for {target}: {e}")
        return False


# Standalone test
if __name__ == "__main__":
    async def main():
        agent = KasaAgent()
        
        print("=" * 50)
        print("Kasa Discovery Test")
        print("=" * 50)
        kasa_devices = await agent.discover_devices()
        print(f"\nKasa devices: {kasa_devices}")
        
        print("\n" + "=" * 50)
        print("Full Network Scan Test")
        print("=" * 50)
        all_devices = await agent.scan_full_network()
        
        print("\nAll devices found:")
        for device in all_devices:
            print(f"  {device['ip']:15s} | {device['vendor'] or 'Unknown':25s} | {device['device_type']:20s} | Ports: {device['open_ports']}")
    
    asyncio.run(main())
