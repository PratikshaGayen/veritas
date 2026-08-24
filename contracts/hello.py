# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""Phase 0 smoke-test contract.

Purpose: prove the deploy path (lint -> deploy -> view call) works before any
real Veritas code is written. See docs/BUILD-PLAN.md task 0.4.
"""

from genlayer import *


class Hello(gl.Contract):
    greeting: str
    deploy_count: u256

    def __init__(self, greeting: str):
        self.greeting = greeting
        self.deploy_count = u256(1)

    @gl.public.view
    def get_greeting(self) -> str:
        return self.greeting

    @gl.public.write
    def set_greeting(self, greeting: str) -> None:
        self.greeting = greeting
