import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional, Dict, List
from concurrent.futures import ThreadPoolExecutor, Future
import asyncio


class TaskStatus(Enum):
    PENDING    = "pending"
    RUNNING    = "running"
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


class TaskPriority(Enum):
    LOW    = 3
    NORMAL = 2
    HIGH   = 1   


@dataclass(order=True)
class Task:
    priority:    int                       
    created_at:  float = field(compare=False)
    task_id:     str   = field(compare=False)
    goal:        str   = field(compare=False)
    status:      TaskStatus = field(compare=False, default=TaskStatus.PENDING)
    result:      Any        = field(compare=False, default=None)
    error:       str        = field(compare=False, default="")
    speak:       Any        = field(compare=False, default=None)   
    on_complete: Any        = field(compare=False, default=None)  
    cancel_flag: threading.Event = field(compare=False, default_factory=threading.Event)
    future:      Optional[Future] = field(compare=False, default=None)  # For async/await support


class TaskQueue:
    """
    Priority-based task queue with configurable concurrency.
    
    Features:
    - Priority ordering (HIGH > NORMAL > LOW)
    - Configurable max concurrent tasks
    - Thread-safe submission, cancellation, status queries
    - Async/await support via futures
    - Proper lock contention avoidance
    - Graceful shutdown
    """
    
    def __init__(self, max_concurrent: int = 2):
        self._queue: List[Task] = []
        self._lock: threading.Lock = threading.Lock()
        self._condition: threading.Condition = threading.Condition(self._lock)
        self._tasks: Dict[str, Task] = {}
        self._running: bool = False
        self._worker_thread: Optional[threading.Thread] = None
        self._max_concurrent = max_concurrent
        self._active_futures: Dict[str, Future] = {}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._agent_executor = None  # Lazy-loaded AgentExecutor

    def _get_executor(self):
        """Lazy-load the AgentExecutor (avoids circular imports)."""
        if self._agent_executor is None:
            from agent.executor import AgentExecutor
            self._agent_executor = AgentExecutor()
        return self._agent_executor

    def start(self) -> None:
        """Start the background worker thread."""
        if self._running:
            return
        
        self._running = True
        
        # Use a thread pool for task execution (avoids thread-per-task overhead)
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_concurrent,
                thread_name_prefix="AgentTask"
            )
        
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="AgentTaskQueue-Scheduler"
        )
        self._worker_thread.start()
        print(f"[TaskQueue] ✅ Started (max_concurrent={self._max_concurrent})")

    def stop(self, timeout: float = 5.0) -> None:
        """
        Gracefully stop the queue.
        Cancels pending tasks, waits for running tasks to complete.
        """
        if not self._running:
            return
        
        print("[TaskQueue] 🔴 Stopping...")
        self._running = False
        
        # Cancel all pending tasks
        with self._lock:
            for task in self._queue:
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
                    task.cancel_flag.set()
            self._queue.clear()
        
        # Notify worker to exit
        with self._condition:
            self._condition.notify_all()
        
        # Shutdown thread pool gracefully
        if self._executor:
            self._executor.shutdown(wait=True, cancel_futures=True)
            self._executor = None
        
        print("[TaskQueue] 🔴 Stopped")

    async def submit_async(
        self,
        goal: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        speak: Callable | None = None,
    ) -> str:
        """
        Submit a task and return a task_id immediately.
        Use get_result_async() to await completion.
        """
        task_id = self.submit(goal=goal, priority=priority, speak=speak)
        return task_id

    async def get_result_async(self, task_id: str, timeout: float = None) -> Any:
        """
        Await the result of a submitted task.
        Raises TimeoutError if timeout expires.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")
            
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if task.status == TaskStatus.COMPLETED:
                    return task.result
                elif task.status == TaskStatus.FAILED:
                    raise RuntimeError(task.error)
                else:
                    raise asyncio.CancelledError("Task was cancelled")
            
            # Create a future if one doesn't exist
            if task.future is None:
                task.future = Future()
        
        # Wait for completion outside the lock
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, task.future.result, timeout
            )
            return result
        except concurrent.futures.TimeoutError:
            raise asyncio.TimeoutError(f"Task {task_id} timed out after {timeout}s")

    def submit(
        self,
        goal: str,
        priority: TaskPriority = TaskPriority.NORMAL,
        speak: Callable | None = None,
        on_complete: Callable | None = None,
    ) -> str:
        """
        Submit a task to the queue.
        
        Args:
            goal: Natural language goal description
            priority: TaskPriority.HIGH, NORMAL, or LOW
            speak: Callback for status updates during execution
            on_complete: Callback (task_id, result) when task finishes
        
        Returns:
            task_id: Unique identifier for status tracking
        """
        task_id = str(uuid.uuid4())[:8]
        task = Task(
            priority=priority.value,
            created_at=time.time(),
            task_id=task_id,
            goal=goal,
            speak=speak,
            on_complete=on_complete,
        )

        with self._condition:
            self._queue.append(task)
            # Sort by priority first, then creation time (oldest first within same priority)
            self._queue.sort(key=lambda t: (t.priority, t.created_at))
            self._tasks[task_id] = task
            self._condition.notify()

        print(f"[TaskQueue] 📥 Task queued: [{task_id}] {goal[:60]}")
        return task_id

    def cancel(self, task_id: str) -> bool:
        """
        Cancel a task by ID.
        Returns True if cancelled, False if already completed/failed.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return False

            task.cancel_flag.set()
            
            # Cancel the future if it exists
            if task.future and not task.future.done():
                task.future.cancel()
            
            task.status = TaskStatus.CANCELLED
            
            # Remove from queue if still pending
            try:
                self._queue.remove(task)
            except ValueError:
                pass
            
            print(f"[TaskQueue] 🚫 Task cancelled: [{task_id}]")
            return True

    def cancel_all_pending(self) -> int:
        """Cancel all pending tasks. Returns count of cancelled tasks."""
        count = 0
        with self._lock:
            for task in list(self._queue):
                if task.status == TaskStatus.PENDING:
                    task.cancel_flag.set()
                    task.status = TaskStatus.CANCELLED
                    count += 1
            self._queue.clear()
        return count

    def get_status(self, task_id: str) -> Optional[Dict]:
        """Get detailed status of a specific task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            return {
                "task_id": task.task_id,
                "goal": task.goal,
                "status": task.status.value,
                "result": task.result,
                "error": task.error,
                "priority": TaskPriority(task.priority).name,
                "created_at": task.created_at,
            }

    def get_all_statuses(self) -> List[Dict]:
        """Get status of all tasks (current and historical)."""
        with self._lock:
            return [
                {
                    "task_id": t.task_id,
                    "goal": t.goal[:80],
                    "status": t.status.value,
                    "priority": TaskPriority(t.priority).name,
                    "error": t.error[:100] if t.error else None,
                }
                for t in sorted(
                    self._tasks.values(),
                    key=lambda t: t.created_at,
                    reverse=True
                )[:50]  # Last 50 tasks
            ]

    def pending_count(self) -> int:
        """Number of tasks waiting to execute."""
        with self._lock:
            return sum(1 for t in self._queue if t.status == TaskStatus.PENDING)

    def active_count(self) -> int:
        """Number of tasks currently executing."""
        with self._lock:
            return len(self._active_futures)

    def is_idle(self) -> bool:
        """True if no tasks are pending or running."""
        return self.pending_count() == 0 and self.active_count() == 0

    def _worker_loop(self) -> None:
        """Main scheduler loop - dispatches tasks to thread pool."""
        while self._running:
            task = None

            with self._condition:
                # Wait for available tasks or shutdown
                while self._running and not self._can_dispatch():
                    self._condition.wait(timeout=1.0)
                
                if not self._running:
                    break
                
                task = self._dispatch_next()
            
            if task:
                # Submit to thread pool (does NOT hold the lock)
                future = self._executor.submit(self._run_task, task)
                
                with self._lock:
                    self._active_futures[task.task_id] = future
                    task.future = future

    def _can_dispatch(self) -> bool:
        """Check if we can dispatch another task (must hold lock)."""
        if self._active_futures:
            # Clean up completed futures
            done = [tid for tid, f in self._active_futures.items() if f.done()]
            for tid in done:
                del self._active_futures[tid]
        
        return len(self._active_futures) < self._max_concurrent and self._next_pending() is not None

    def _next_pending(self) -> Optional[Task]:
        """Get the next pending task (must hold lock)."""
        for task in self._queue:
            if task.status == TaskStatus.PENDING and not task.cancel_flag.is_set():
                return task
        return None

    def _dispatch_next(self) -> Optional[Task]:
        """Mark next task as running and return it (must hold lock)."""
        task = self._next_pending()
        if task:
            task.status = TaskStatus.RUNNING
            try:
                self._queue.remove(task)
            except ValueError:
                pass
        return task

    def _run_task(self, task: Task) -> None:
        """
        Execute a single task. Runs in thread pool.
        Does NOT hold any locks during execution.
        """
        print(f"[TaskQueue] ▶️ Running: [{task.task_id}] {task.goal[:60]}")
        
        try:
            executor = self._get_executor()
            result = executor.execute(
                goal=task.goal,
                speak=task.speak,
                cancel_flag=task.cancel_flag,
            )

            with self._lock:
                if task.cancel_flag.is_set():
                    task.status = TaskStatus.CANCELLED
                else:
                    task.status = TaskStatus.COMPLETED
                    task.result = result

        except Exception as e:
            with self._lock:
                if task.cancel_flag.is_set():
                    task.status = TaskStatus.CANCELLED
                else:
                    task.status = TaskStatus.FAILED
                    task.error = str(e)
            print(f"[TaskQueue] ❌ Failed: [{task.task_id}] {e}")

        finally:
            # Clean up active futures (executor future is handled automatically)
            with self._lock:
                self._active_futures.pop(task.task_id, None)
            
            # Trigger on_complete callback
            if task.on_complete and task.status == TaskStatus.COMPLETED:
                try:
                    task.on_complete(task.task_id, task.result)
                except Exception as e:
                    print(f"[TaskQueue] ⚠️ on_complete callback error: {e}")

            print(f"[TaskQueue] ✅ Completed: [{task.task_id}]")

        # Notify scheduler that a slot freed up
        with self._condition:
            self._condition.notify()


# Global singleton
_queue: Optional[TaskQueue] = None
_queue_started: bool = False
_queue_lock: threading.Lock = threading.Lock()


def get_queue(max_concurrent: int = 2) -> TaskQueue:
    """Get or create the global TaskQueue singleton."""
    global _queue, _queue_started
    
    with _queue_lock:
        if _queue is None:
            _queue = TaskQueue(max_concurrent=max_concurrent)
        
        if not _queue_started:
            _queue.start()
            _queue_started = True
    
    return _queue


def reset_queue():
    """Reset the global queue (useful for testing or restart)."""
    global _queue, _queue_started
    
    with _queue_lock:
        if _queue:
            _queue.stop()
        _queue = None
        _queue_started = False