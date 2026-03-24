"""
Alpha-Stream Architect: AI Hedge Fund Engine.
Institutional-grade multi-agent system for market analysis.
"""

__version__ = "1.0.0"
__author__ = "Alpha-Stream Architect"

# Edge Logic: We keep this file minimal. 
# Explicitly importing agents or graphs here can cause circular dependencies 
# when those sub-modules try to import from each other via 'src'.