"""Pywer Plugin Architecture.

Provides packaging, virtual in-memory loading, lifecycle management,
and runtime APIs for Bedrock server plugins.
"""

from .compiler import PluginCompileError, PluginCompiler

__all__ = [
    "PluginCompileError",
    "PluginCompiler",
]
