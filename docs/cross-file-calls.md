# Phase 15: broader approximate calls

Call candidates now include explicit `from module import function as alias`, module imports such as `import module as m; m.function()`, relative imports, and `self.method()` / `cls.method()` inside a known class. Module and definition collisions stay ambiguous. Arbitrary object types, wildcard imports, re-export chains, inheritance dispatch, parameter shadowing, and runtime rebinding are not resolved. Every target remains a syntactic candidate, not proof of execution.

Migration `003_call_origins` stores each call's original lexical target and resolution. Before changing files, those origins replace cross-file suggestions; parsing then recalculates imported and receiver candidates against the full current inventory. This avoids dangling foreign keys and stale suggestions when a target changes or disappears, while retaining unchanged caller and call IDs. The cache-format upgrade parses old indexes once.

The Calls tab can navigate to targets in another file through the same commit-checked symbol/source flow. Tests cover aliases, receiver methods, ambiguous definitions, target removal, and unchanged call identities.
