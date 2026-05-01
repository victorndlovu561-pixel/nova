"""
ContextScopeEngine - Understands the SCOPE of user questions.

"World" → global scope, not local system
"Mountains" → geology scope, not hardware  
"Network" → check ALL network devices, not just Kasa
"""

from typing import Dict, List, Set


class ContextScopeEngine:
    """
    Understands the SCOPE of user questions.
    """
    
    SCOPE_HIERARCHY = {
        "local": ["cpu", "memory", "disk", "file", "window", "app"],
        "device": ["computer", "laptop", "screen", "keyboard", "mouse"],
        "room": ["light", "temperature", "printer", "speaker", "desk"],
        "home": ["smart home", "kasa", "tv", "phone", "kitchen", "door"],
        "network": ["wifi", "router", "device", "ip", "connected", "online", "scan", "check network"],
        "neighborhood": ["outside", "street", "neighbor", "local area"],
        "city": ["weather", "traffic", "event", "local news"],
        "country": ["government", "policy", "national", "economy"],
        "world": ["global", "international", "world", "earth", "planet", "threat", "worldwide"],
        "universe": ["cosmos", "space", "star", "galaxy", "nasa"],
    }
    
    KNOWLEDGE_DOMAINS = {
        "geology": ["mountain", "stone", "rock", "mineral", "earth", "volcano", "cave"],
        "hardware": ["cpu", "gpu", "ram", "disk", "processor", "memory", "motherboard"],
        "biology": ["animal", "plant", "human", "cell", "dna", "species"],
        "astronomy": ["planet", "star", "galaxy", "moon", "sun", "orbit"],
        "technology": ["software", "code", "app", "api", "server", "cloud"],
        "security": ["virus", "threat", "hack", "attack", "defense", "protect", "monitor"],
    }
    
    def detect_scope_and_domain(self, text: str) -> Dict:
        """Detect both scope and knowledge domain from user input."""
        text_lower = text.lower()
        words = set(text_lower.split())
        
        # Check multi-word phrases
        phrases = []
        words_list = text_lower.split()
        for i in range(len(words_list)):
            for j in range(i+1, min(i+4, len(words_list)+1)):
                phrase = " ".join(words_list[i:j])
                phrases.append(phrase)
        
        # Detect scope
        scope_scores = {}
        for scope, keywords in self.SCOPE_HIERARCHY.items():
            score = 0
            for kw in keywords:
                if kw in text_lower:
                    score += 2  # Higher weight for matches
                for phrase in phrases:
                    if kw == phrase:
                        score += 3  # Even higher for phrase matches
            scope_scores[scope] = score
        
        detected_scope = max(scope_scores, key=scope_scores.get) if max(scope_scores.values()) > 0 else "local"
        
        # Detect knowledge domain
        domain_scores = {}
        for domain, keywords in self.KNOWLEDGE_DOMAINS.items():
            domain_scores[domain] = sum(1 for kw in keywords if kw in text_lower)
        
        detected_domain = max(domain_scores, key=domain_scores.get) if max(domain_scores.values()) > 0 else "general"
        
        return {
            "scope": detected_scope,
            "domain": detected_domain,
            "scope_score": scope_scores[detected_scope],
            "domain_score": domain_scores[detected_domain],
        }
    
    def generate_context_prompt(self, user_text: str, analysis: Dict) -> str:
        """Generate a context injection for the model based on scope/domain."""
        prompts = []
        
        scope = analysis["scope"]
        if scope == "world":
            prompts.append(
                "SCOPE: The user is asking about global/world-scale matters. "
                "Think internationally, geopolitically, or globally. "
                "Do NOT respond with local system information like CPU or disk."
            )
        elif scope == "home":
            prompts.append(
                "SCOPE: The user is asking about home/domestic matters. "
                "Think about smart devices, home network, connected appliances. "
                "Check ALL network devices using network scanning tools."
            )
        elif scope == "network":
            prompts.append(
                "SCOPE: The user is asking about network connectivity. "
                "Consider ALL connected devices: phones, TVs, routers, IoT devices. "
                "Use network scanning tools to find every device on the network."
            )
        
        domain = analysis["domain"]
        if domain == "geology":
            prompts.append(
                "DOMAIN: The user is discussing geology/earth science. "
                "When they mention 'mountains', discuss stone, rock formations, "
                "plate tectonics, erosion—not computer hardware."
            )
        elif domain == "security":
            prompts.append(
                "DOMAIN: The user is discussing security/threats. "
                "Consider cybersecurity, network threats, malware, "
                "vulnerabilities at the appropriate scope level."
            )
        
        return "\n".join(prompts) if prompts else ""
