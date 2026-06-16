# Parsing approach and trade-offs

This note explains how `sm64.sql` reads the decomp today and when it would make
sense to move to a "real" C parser such as tree-sitter or libclang.

## What we are actually parsing

The data this tool wants is not ordinary C. It lives in:

- **Macro invocations** — `OBJECT(MODEL_BOO, x, y, z, ..., bhvParam, bhvFoo)` in
  `levels/*/script.c`, `MACRO_OBJECT(...)` in `macro.inc.c`. These are
  preprocessor macros that expand into a level-command byte stream; the `.inc.c`
  files are not standalone translation units.
- **Preprocessor defines** — `#define MODEL_BOO 0x1F` in `model_ids.h`, some of
  which *alias* another define (`#define MODEL_WF_GIANT_POLE
  MODEL_LEVEL_GEOMETRY_0D`).
- **Enums and array initializers** — `enum MacroPresets { ... }` and
  `static struct MacroPreset sMacroObjectPresets[] = { { bhv, model, param }, ... }`.

Two things follow from this:

1. The arguments are *symbolic* (`MODEL_BOO`, `bhvGoomba`, `macro_goomba`). The
   value of the resulting database is keeping those names, because they are what
   a human or another tool reasons about. We do **not** want to expand them to
   integers in the common case.
2. There are really two separate problems hiding behind "parse the decomp":
   **structural parsing** (find the macro calls and split their arguments) and
   **semantic resolution** (turn `BPARAM2(41)` into `0x290000`, or resolve an
   aliased model id). They have different best tools.

## The options

### A. Line / bracket-aware text parsing (current)

`src/sm64_sql/parse_utils.py` matches a macro by name, walks to its matching
close paren, and splits the arguments on *top-level* commas (commas outside any
brackets), stripping `/* */` and `//` comments.

- **Pros:** zero dependencies, fast, trivial to read, and the decomp is
  clang-formatted so the surface is highly regular. It parses a full current
  `n64decomp/sm64` checkout with every object/macro/model/preset row accounted
  for.
- **Cons:** it is text matching, not a grammar. It assumes single-line macro
  calls and known macro names. Wildly reformatted or multi-line input would
  need more care.

### B. tree-sitter (`tree-sitter-c`)

An error-tolerant concrete-syntax-tree parser. `OBJECT(...)` becomes a
`call_expression` with an `argument_list`, regardless of whitespace, comments,
or line breaks, and unknown identifiers/macros simply appear as nodes rather
than causing failures.

- **Pros:** robust structural parsing for free — exactly the
  `split_top_level` / `extract_macro_args` job, but grammar-backed and
  multi-line safe. pip-installable (`tree-sitter` + a C grammar). Error tolerant,
  so it does not need the macros defined or the file to compile.
- **Cons:** a native dependency, and it still does **not** evaluate anything:
  `BPARAM2(41)` is still a `call_expression` you read as text, `MODEL_BOO` is
  still an identifier. It replaces the ~40 lines of arg-splitting we already
  have and which already cover 100% of the decomp.

### C. Full preprocessor + C frontend (libclang / pycparser)

Actually run the C preprocessor and parse the result, so macros expand and
constants resolve to numbers.

- **Pros:** the only approach that gives true semantics — real behavior-param
  values, resolved enums, etc.
- **Cons:** heavyweight and a poor fit for the goal. It needs the decomp's
  include paths and compile flags, and expanding `OBJECT(...)` produces the
  level-command **byte stream**, from which the nice `(model, pos, behavior)`
  fields are *harder* to recover than from the source macro. It would also throw
  away the symbolic names that make the database useful. libclang needs a system
  clang; pycparser needs fake headers for compiler extensions.

## Recommendation

- **Keep the text parser as the default.** For this small, regular, flat surface
  (a handful of macro names, one enum, one array, one set of defines) the
  marginal robustness of a grammar is low, and the parsing seam in
  `parse_utils.py` keeps a future swap cheap.
- **Reach for tree-sitter when the scope grows** — multi-line macro calls,
  supporting many decomp forks with divergent formatting, or extracting much
  more of the C (behavior scripts, geo layouts, collision, the level command
  script) where the structure is genuinely nested and irregular. At that point
  `tree-sitter-c` is clearly the right tool, and far better than libclang,
  because we want a tolerant CST over un-preprocessed source, not a semantic AST
  of a translation unit.
- **Do not adopt libclang/pycparser for extraction.** The one place real
  evaluation helps is resolving symbolic constants to numbers (behavior params,
  aliased/expression model ids). That is a small, targeted *constant-resolution*
  problem — best solved with a tiny expression evaluator over the `#define` and
  `enum` tables we already build (this is how aliased model ids are resolved
  today in `model.py`), not a full C frontend.

In short: the parser backend is not the bottleneck. The interesting future work
is semantic resolution, which no choice of parser solves on its own.
