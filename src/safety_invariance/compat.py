from __future__ import annotations

from typing import Any


def ensure_torch_module_set_submodule(torch_module: Any) -> bool:
    """Backfill nn.Module.set_submodule for older PyTorch builds.

    Newer Transformers versions may call ``set_submodule`` while loading model
    weights. RunPod's stable PyTorch 2.4 CUDA 12.4 image does not expose that
    method, so we provide the minimal compatible behavior on nn.Module.
    Returns True when a shim was installed.
    """

    module_cls = torch_module.nn.Module
    if hasattr(module_cls, "set_submodule"):
        return False

    def set_submodule(self, target: str, module: Any, strict: bool = False) -> None:
        if not isinstance(target, str):
            raise TypeError(f"target should be a string, got {type(target).__name__}")
        if target == "":
            raise ValueError("Cannot set the root module through set_submodule.")
        atoms = target.split(".")
        parent = self
        for item in atoms[:-1]:
            if not hasattr(parent, item):
                if strict:
                    raise AttributeError(f"{type(parent).__name__} has no child module '{item}'")
                raise AttributeError(f"Cannot set submodule '{target}': missing parent '{item}'")
            parent = getattr(parent, item)
        leaf = atoms[-1]
        if strict and not hasattr(parent, leaf):
            raise AttributeError(f"{type(parent).__name__} has no child module '{leaf}'")
        setattr(parent, leaf, module)

    module_cls.set_submodule = set_submodule
    return True
