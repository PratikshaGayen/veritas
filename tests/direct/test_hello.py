"""Phase 0 smoke test — proves the direct-mode harness deploys and calls a real
contract before any Veritas code exists. See docs/BUILD-PLAN.md task 0.4/0.5.
"""


def test_deploy_and_read_greeting(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/hello.py", args=["hello from phase 0"])
    direct_vm.sender = direct_alice

    assert contract.get_greeting() == "hello from phase 0"


def test_write_updates_greeting(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy("contracts/hello.py", args=["initial"])
    direct_vm.sender = direct_alice

    contract.set_greeting("updated")

    assert contract.get_greeting() == "updated"
