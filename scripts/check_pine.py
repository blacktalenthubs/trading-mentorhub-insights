"""Catch undeclared identifiers in Pine v5 — the class TradingView catches at compile
time and my structural checks don't (yV in #1044, tagOff in #1073)."""
import re, sys
BUILTIN = set('''close open high low volume time bar_index na true false math array str label line box table color
size shape location yloc input request ticker syminfo timeframe barstate ta nz barmerge order position extend
plotshape plot indicator alert alertcondition int float bool string var if else for while break continue and or not
to in by fill hline bgcolor barcolor dayofmonth month year hour minute second timenow syminfo'''.split())
NAMED_ARG = re.compile(r'[(,]\s*([A-Za-z_]\w*)\s*=[^=]')

def check(path):
    src = open(path).read()
    code = re.sub(r'"[^"\n]*"', '""', src)
    code = "\n".join(l.split("//")[0] for l in code.split("\n"))
    code = re.sub(r'#[0-9A-Fa-f]{6,8}', '0', code)              # hex colours
    declared = set(re.findall(r'^\s*(?:var\s+\w+(?:\[\])?\s+)?([A-Za-z_]\w*)\s*:?=', code, re.M))
    declared |= set(re.findall(r'^([A-Za-z_]\w*)\s*\(', code, re.M))
    declared |= set(re.findall(r'for\s+([A-Za-z_]\w*)\s*(?:=|in)', code))
    for grp in re.findall(r'\[([^\]]+)\]\s*=', code):
        declared |= {g.strip() for g in grp.split(",")}
    for params in re.findall(r'^[A-Za-z_]\w*\(([^)]*)\)\s*=>', code, re.M):   # fn params
        declared |= {re.sub(r'^\s*(?:simple |series )?\w+(?:\[\])?\s+', '', p).strip() for p in params.split(",")}
    named = set(NAMED_ARG.findall(code))
    used = set()
    for m in re.finditer(r'\b([A-Za-z_]\w*)\b', code):
        if code[max(0, m.start()-1):m.start()] == "." or code[m.end():m.end()+1] == ".":
            continue                                   # namespace head or member (format.mintick)
        used.add(m.group(1))
    missing = sorted(u for u in used - declared - BUILTIN - named)
    print(f"  {path.split('/')[-1]:34} {'UNDECLARED -> ' + ', '.join(missing) if missing else 'clean ✓'}")

print("Pine undeclared-identifier scan:")
for p in sys.argv[1:]:
    check(p)
