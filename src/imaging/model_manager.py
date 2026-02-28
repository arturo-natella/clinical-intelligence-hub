"""
Clinical Intelligence Hub — Sequential Model Manager

Manages loading and unloading of AI models to stay within
the 64GB memory budget. Only one large model runs at a time.

Key design:
  - Memory tracking via psutil
  - gc.collect() + torch.mps.empty_cache() between models
  - Peak memory target: under 36GB (leaving room for OS + apps)
  - Models loaded sequentially, never concurrently
"""

import gc
import logging
import time
from typing import Optional

logger = logging.getLogger("CIH-ModelManager")

# Memory budget (bytes)
PEAK_MEMORY_TARGET_GB = 36
PEAK_MEMORY_TARGET_BYTES = PEAK_MEMORY_TARGET_GB * 1024 * 1024 * 1024


class ModelManager:
    """
    Manages sequential model loading/unloading for the 6-pass pipeline.

    Ensures only one large model is in memory at a time and cleans up
    between passes to prevent OOM on the 64GB Mac Mini.
    """

    def __init__(self):
        self._current_model: Optional[str] = None

    def get_memory_usage_gb(self) -> float:
        """Get current process memory usage in GB."""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / (1024 ** 3)
        except ImportError:
            logger.debug("psutil not installed — memory tracking unavailable")
            return 0.0

    def get_system_memory_gb(self) -> dict:
        """Get system-wide memory stats."""
        try:
            import psutil
            vm = psutil.virtual_memory()
            return {
                "total_gb": vm.total / (1024 ** 3),
                "available_gb": vm.available / (1024 ** 3),
                "used_percent": vm.percent,
            }
        except ImportError:
            return {"total_gb": 0, "available_gb": 0, "used_percent": 0}

    def check_memory_budget(self) -> bool:
        """Check if we're within the memory budget."""
        usage = self.get_memory_usage_gb()
        target = PEAK_MEMORY_TARGET_GB
        within_budget = usage < target
        if not within_budget:
            logger.warning(f"Memory usage {usage:.1f}GB exceeds target {target}GB")
        return within_budget

    def cleanup_between_models(self):
        """
        Aggressive memory cleanup between model loads.
        Called after each pass to free memory before loading the next model.
        """
        logger.info("Cleaning up memory between model passes...")
        before = self.get_memory_usage_gb()

        # Python garbage collection
        gc.collect()
        gc.collect()  # Second pass catches reference cycles

        # PyTorch MPS cache (Apple Silicon GPU memory)
        try:
            import torch
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
                logger.debug("Cleared PyTorch MPS cache")
        except (ImportError, AttributeError):
            pass

        # Small delay to let OS reclaim memory
        time.sleep(0.5)

        after = self.get_memory_usage_gb()
        freed = before - after
        if freed > 0.1:
            logger.info(f"Freed {freed:.1f}GB (was {before:.1f}GB, now {after:.1f}GB)")
        else:
            logger.debug(f"Memory: {after:.1f}GB (minimal change)")

    def unload_ollama_model(self, model_name: str):
        """
        Explicitly unload an Ollama model from memory.
        Uses keep_alive: "0" to force immediate unload.
        """
        try:
            import ollama
            ollama.generate(model=model_name, prompt="", keep_alive="0")
            logger.info(f"Unloaded Ollama model: {model_name}")
            self._current_model = None
        except Exception as e:
            logger.debug(f"Failed to unload {model_name}: {e}")

    def prepare_for_model(self, model_name: str, expected_memory_gb: float):
        """
        Prepare the system for loading a new model.
        Unloads current model and checks memory budget.
        """
        # Unload current model if different
        if self._current_model and self._current_model != model_name:
            self.unload_ollama_model(self._current_model)
            self.cleanup_between_models()

        # Check available memory
        sys_mem = self.get_system_memory_gb()
        available = sys_mem.get("available_gb", 0)

        if available < expected_memory_gb:
            logger.warning(
                f"Available memory ({available:.1f}GB) may be insufficient "
                f"for {model_name} (needs ~{expected_memory_gb}GB). "
                f"Proceeding anyway — OS may use swap."
            )

        self._current_model = model_name
        logger.info(f"Ready to load: {model_name} (expected ~{expected_memory_gb}GB)")

    def full_cleanup(self):
        """
        Full cleanup after all model passes are complete.
        Called at the end of the local extraction phase.
        """
        if self._current_model:
            self.unload_ollama_model(self._current_model)

        self.cleanup_between_models()

        mem = self.get_memory_usage_gb()
        logger.info(f"Full cleanup complete. Process memory: {mem:.1f}GB")
