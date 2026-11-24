#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
port_ios15.py — 在 CI 里把 DouDuo 从 iOS 26 部署目标机械降级到 iOS 15。

做什么：
  1) project.yml 部署目标 26.0 -> 15.0
  2) 注入兼容层 scripts/DYCompat.swift 到 DouDuo/
  3) 删除 / 替换 iOS 16+ 才有的 SwiftUI API（视觉降级，功能保留）
  4) NavigationStack -> DYStack(NavigationView)
  5) Tab(value:) -> DYTab(tabItem + tag)
  6) ContentUnavailableView -> DYContentUnavailableView
  7) onChange 双参 -> onChangeCompat
  8) @Observable -> ObservableObject + @Published

用法：python3 scripts/port_ios15.py [repo_root]
"""

import os
import re
import shutil
import sys
import pathlib

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
APP = ROOT / "DouDuo"

STRIP_TOKENS = [
    ".glassEffect",
    ".scrollIndicators",
    ".scrollContentBackground",
    ".toolbarBackground",
    ".scrollEdgeEffectHidden",
    ".scrollEdgeEffectStyle",
    ".scrollClipDisabled",
    ".scrollBounceBehavior",
    ".containerRelativeFrame",
    ".scrollTargetLayout",
    ".scrollTargetBehavior",
    ".scrollPosition",
    ".safeAreaPadding",
    ".contentTransition",
    ".sensoryFeedback",
    ".presentationDetents",
    ".presentationCornerRadius",
    ".onScrollGeometryChange",
    ".tabBarMinimizeBehavior",
    ".scrollTransition",
    ".visualEffect",
    ".defaultScrollAnchor",
    ".scrollDismissesKeyboard",
    ".presentationDragIndicator",
    ".presentationCompactAdaptation",
    ".presentationBackground",
    ".onGeometryChange",
    ".contentMargins",
    ".symbolEffect",
    ".containerBackground",
    ".backgroundStyle",
    ".toolbarVerticalBehavior",
    ".toolbarVerticalCompressionBehavior",
    ".toolbarMinimizationBehavior",
    ".axisBehavior",
    ".visibilityPriority",
    ".onHingeChange",
    ".coordinateSpace",
    ".toolbarVisibility",
]


def _skip_space(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t\r\n":
        i += 1
    return i


def _match_brace(s: str, i: int) -> int:
    """i 指向 '{'，返回配对 '}' 的下标"""
    depth = 0
    quote = None
    while i < len(s):
        ch = s[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        else:
            if ch == '"':
                quote = '"'
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return i


def _eat_trailing_closures(s: str, i: int) -> int:
    """吃掉紧跟其后的尾随闭包 `{...}` 以及 `label: {...}` 形式"""
    while True:
        j = _skip_space(s, i)
        if j < len(s) and s[j] == "{":
            i = _match_brace(s, j) + 1
            continue
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*\s*:\s*\{", s[j:])
        if m:
            brace = j + m.end() - 1
            i = _match_brace(s, brace) + 1
            continue
        return i


def strip_segment(src: str, token: str) -> str:
    """删除 `.token(...)` 整段调用（含尾随闭包），保持链式调用合法。"""
    out = []
    i = 0
    n = len(src)
    while True:
        j = src.find(token, i)
        if j == -1:
            out.append(src[i:])
            break
        k = src.find("(", j)
        if k == -1:
            out.append(src[i : j + len(token)])
            i = j + len(token)
            continue
        depth = 0
        p = k
        quote = None
        closed = False
        while p < n:
            ch = src[p]
            if quote:
                if ch == "\\":
                    p += 2
                    continue
                if ch == quote:
                    quote = None
            else:
                if ch == '"':
                    quote = '"'
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        closed = True
                        break
            p += 1
        out.append(src[i:j])
        i = _eat_trailing_closures(src, p + 1) if closed else p + 1
    return "".join(out)


TEXT_REPLACEMENTS = [
    (".onChange(of:", ".onChangeCompat(of:"),
    ("NavigationStack(", "DYStack("),
    ("NavigationStack", "DYStack"),
    ("ContentUnavailableView(", "DYContentUnavailableView("),
    (".buttonStyle(.glass)", ".buttonStyle(.plain)"),
    ("@Bindable ", "@ObservedObject "),
    ("Mutex(", "DYMutex("),
    ("Mutex<", "DYMutex<"),
    ("URL.temporaryDirectory", "FileManager.default.temporaryDirectory"),
    ("[(CGFloat, CGFloat, Duration)]", "[(CGFloat, CGFloat, UInt64)]"),
    ("fill(.separator)", "fill(Color(UIColor.separator))"),
    (".buttonStyle(.glassProminent)", ".buttonStyle(.borderedProminent)"),
    ("accent.mix(with: .white, by: 0.4)", "accent"),
    ("@ContentBuilder", "@ViewBuilder"),
    ("ContinuousClock.Instant", "Date"),
    (", layoutDirectionBehavior: .fixed", ""),
    (", .bottomBar)", ")"),
]

BLOCK_FIXES = [
    # 裸调用形态的 iOS 26/27 修饰符（在 if 分支开头，没有前导点）
    (
        re.compile(r"\n[ \t]*toolbarVisibility\([^\n]*\)"),
        "",
    ),
    # 直播：折痕状态（DeviceHinge 只存在于 iOS 27 SDK）
    (
        re.compile(r"@available\(iOS 27\.1, \*\)\nprivate func dyLiveHingeStatus[\s\S]*?\n\}\n"),
        "",
    ),
    (
        re.compile(
            r"if #available\(iOS 27\.1, \*\) \{\s*\n\s*onHingeChange \{ _, context in apply\(dyLiveHingeStatus\(context\.hinge\)\) \}\s*\n\s*\} else \{\s*\n\s*self\s*\n\s*\}",
            re.M,
        ),
        "        self",
    ),
    # 导航栏：UITab / selectedTab / shouldSelectTab 仅 iOS 18+
    (
        re.compile(
            r"\n\s*func tabBarController\(_ controller: UITabBarController, shouldSelectTab tab: UITab\) -> Bool \{[\s\S]*?\n        \}\n",
            re.M,
        ),
        "\n",
    ),
    # 关注元数据缓存：私有成员导致 memberwise init 不可见
    (
        re.compile(r"(struct DYFollowMetadataCache \{\n\s+var ttl: TimeInterval)"),
        lambda m: m.group(1) + "\n\n    init(ttl: TimeInterval) { self.ttl = ttl }",
    ),
]

REGEX_REPLACEMENTS = [
    # Task.sleep(for: .milliseconds(x)) -> nanoseconds
    (
        re.compile(r"Task\.sleep\(for:\s*\.milliseconds\(((?:[^()]|\([^()]*\))*)\)\)"),
        lambda m: f"Task.sleep(nanoseconds: UInt64(({m.group(1)}) * 1_000_000))",
    ),
    (
        re.compile(r"Task\.sleep\(for:\s*\.seconds\(((?:[^()]|\([^()]*\))*)\)\)"),
        lambda m: f"Task.sleep(nanoseconds: UInt64(({m.group(1)}) * 1_000_000_000))",
    ),
    (re.compile(r"Task\.sleep\(for:\s*step\.2\)"), lambda m: "Task.sleep(nanoseconds: UInt64(step.2))"),
    (re.compile(r"(?<![\d_])\.milliseconds\(([0-9]+)\)"), lambda m: f"UInt64({m.group(1)}) * 1_000_000"),
    # a.duration(to: .now) < .seconds(x) -> 时间间隔比较
    (
        re.compile(r"([A-Za-z0-9_.]+)\.duration\(to:\s*\.now\)\s*<\s*\.seconds\(([^()]*)\)"),
        lambda m: f"Date().timeIntervalSince({m.group(1)}) < ({m.group(2)})",
    ),
    (re.compile(r"= \((target),\s*\.now\)"), lambda m: f"= ({m.group(1)}, Date())"),
    # LabeledContent -> 兼容实现
    (re.compile(r"(?<!DY)LabeledContent"), lambda m: "DYLabeledContent"),
    # AnyLayout -> 兼容规格
    (
        re.compile(r"AnyLayout\(VStackLayout\((?:alignment:\s*[^,)]+,?\s*)?spacing:\s*([^)]*)\)\)"),
        lambda m: f"DYAnyLayoutSpec(vertical: true, spacing: {m.group(1)})",
    ),
    (
        re.compile(r"AnyLayout\(HStackLayout\((?:alignment:\s*[^,)]+,?\s*)?spacing:\s*([^)]*)\)\)"),
        lambda m: f"DYAnyLayoutSpec(vertical: false, spacing: {m.group(1)})",
    ),
    # .lineLimit(n, reservesSpace: true)
    (re.compile(r"\.lineLimit\(([^,()]+), reservationspace:\s*true\)"), lambda m: f".lineLimit({m.group(1)})"),
    (re.compile(r"\.lineLimit\(([^,()]+), reservesSpace:\s*true\)"), lambda m: f".lineLimit({m.group(1)})"),
    # Text(...).foregroundStyle(...) -> foregroundColor
    (re.compile(r"(Text\([^()]*\))\.foregroundStyle\("), lambda m: f"{m.group(1)}.foregroundColor("),
]

TAB_RE = re.compile(
    r'Tab\("([^"]+)",\s*systemImage:\s*"([^"]+)",\s*value:\s*([A-Za-z0-9_.]+)\)'
)

OBSERVABLE_RE = re.compile(r"@Observable\s*")


def convert_observables(text: str):
    """@Observable -> ObservableObject + @Published，返回 (新文本, 类名列表)"""
    if "@Observable" not in text:
        return text, []

    # 先记下每个 @Observable 后面紧跟的 class 名（只改这些类，别误伤同文件其它类）
    names = []
    for m in OBSERVABLE_RE.finditer(text):
        nxt = text[m.end() : m.end() + 400]
        cm = re.search(r"class[ \t]+([A-Za-z0-9_]+)", nxt)
        if cm and cm.group(1) not in names:
            names.append(cm.group(1))

    text = OBSERVABLE_RE.sub("", text)
    text = text.replace("@ObservationIgnored ", "").replace("@ObservationIgnored", "")

    decl_tpl = re.compile(
        r"(?m)^([ \t]*)((?:@\w+[ \t]+)*(?:final[ \t]+)?)class[ \t]+("
        + "|".join(re.escape(n) for n in names)
        + r")[ \t]*(?::([^\n{]*))?[ \t]*\{"
    )

    def decl_sub(m):
        indent, attrs, name, inherits = m.group(1), m.group(2), m.group(3), m.group(4)
        tail = (
            f": ObservableObject, {inherits.strip()}"
            if inherits and inherits.strip()
            else ": ObservableObject"
        )
        return f"{indent}{attrs}class {name}{tail} {{"

    text = decl_tpl.sub(decl_sub, text)

    # 给类里一层的存储属性加 @Published
    for name in names:
        body_re = re.compile(
            r"class[ \t]+" + re.escape(name) + r"[^\{]*\{"
        )
        mm = body_re.search(text)
        if not mm:
            continue
        start = mm.end() - 1
        depth = 0
        end = start
        for p in range(start, len(text)):
            if text[p] == "{":
                depth += 1
            elif text[p] == "}":
                depth -= 1
                if depth == 0:
                    end = p
                    break
        body = text[start + 1 : end]
        new_lines = []
        inner = 0
        for line in body.split("\n"):
            st = line.strip()
            if inner == 0 and re.match(r"^\s+(?:@\w+[^\n]*\s+)?(?:private\(set\)\s+)?var\s+[A-Za-z0-9_]", line):
                if not st.endswith("{") and "{" not in st and "didSet" not in st:
                    line = re.sub(r"^(\s+)", r"\1@Published ", line, count=1)
            inner += line.count("{") - line.count("}")
            new_lines.append(line)
        text = text[: start + 1] + "\n".join(new_lines) + text[end:]
    return text, names


def main():
    if not APP.is_dir():
        sys.exit(f"找不到源码目录: {APP}")

    # 1) 部署目标
    proj = ROOT / "project.yml"
    if proj.exists():
        s = proj.read_text(encoding="utf-8")
        tgt = os.environ.get("DEPLOY_TARGET", "16.0")
        s2 = re.sub(r'(iOS:\s*)[\'"]?[0-9]+(?:\.[0-9]+)*[\'"]?', lambda m: m.group(1) + '"' + tgt + '"', s, count=1)
        if s2 != s:
            proj.write_text(s2, encoding="utf-8")
            print(f"[ok] project.yml deploymentTarget -> {tgt}")

    # 2) 兼容层
    compat = None
    for cand in (ROOT / "DYCompat.swift", ROOT / "scripts" / "DYCompat.swift"):
        if cand.exists():
            compat = cand
            break
    if compat is not None:
        shutil.copy(compat, APP / "DYCompat.swift")
        print(f"[ok] 注入 DYCompat.swift (来自 {compat})")

    # 3) 逐文件改造
    stat = {"strip": 0, "tab": 0, "obs": 0, "files": 0}
    obs_names = set()

    for path in sorted(APP.rglob("*.swift")):
        if path.name == "DYCompat.swift":
            continue
        raw = path.read_text(encoding="utf-8")
        orig = raw

        for token in STRIP_TOKENS:
            if token in raw:
                raw = strip_segment(raw, token)
                stat["strip"] += 1

        for a, b in TEXT_REPLACEMENTS:
            if a in raw:
                raw = raw.replace(a, b)

        raw, m = TAB_RE.subn(r'DYTabItem("\1", systemImage: "\2", value: \3)', raw)
        stat["tab"] += m

        for rx, fn in REGEX_REPLACEMENTS:
            raw = rx.sub(fn, raw)

        for rx, fn in BLOCK_FIXES:
            raw = rx.sub(fn, raw)

        raw, names = convert_observables(raw)
        if names:
            obs_names.update(names)
            stat["obs"] += 1

        if raw != orig:
            path.write_text(raw, encoding="utf-8")
            stat["files"] += 1

    # 4) @State -> @StateObject（只针对持有 @Observable 模型的地方）
    for name in sorted(obs_names):
        for path in APP.rglob("*.swift"):
            if path.name == "DYCompat.swift":
                continue
            s = path.read_text(encoding="utf-8")
            lines = s.split("\n")
            touched = False
            for i, line in enumerate(lines):
                if "@State private var" not in line:
                    continue
                if (f"= {name}(" in line) or (f"= .init(" in line and f": {name}" in line) or (f": {name} =" in line):
                    lines[i] = line.replace("@State private var", "@StateObject private var", 1)
                    touched = True
            if touched:
                path.write_text("\n".join(lines), encoding="utf-8")

    print(f"[ok] 改造完成: 文件 {stat['files']} 个, 修饰符段 {stat['strip']}, Tab {stat['tab']}, @Observable {stat['obs']}")
    print(f"[i] 发现的 @Observable 类: {sorted(obs_names)}")


if __name__ == "__main__":
    main()
