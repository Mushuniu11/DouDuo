//
//  DYCompat.swift
//  iOS 15 / 16 兼容层（由 CI 注入，不手动改动业务代码）
//

import SwiftUI
import UIKit

// MARK: - onChange（iOS 17 双参闭包 -> iOS 15 可用的等价实现）

struct DYOnChangeCompatBox<V: Equatable>: ViewModifier {
    let value: V
    let initial: Bool
    let action: (V, V) -> Void

    @State private var previous: V?
    @State private var didAppear = false

    func body(content: Content) -> some View {
        content
            .onAppear {
                guard !didAppear else { return }
                didAppear = true
                let old = previous ?? value
                previous = value
                if initial { action(old, value) }
            }
            .onChange(of: value) { newValue in
                let old = previous ?? newValue
                previous = newValue
                action(old, newValue)
            }
    }
}

extension View {
    /// 双参数版本（old, new）
    func onChangeCompat<V: Equatable>(
        of value: V,
        initial: Bool = false,
        _ action: @escaping (V, V) -> Void
    ) -> some View {
        modifier(DYOnChangeCompatBox(value: value, initial: initial, action: action))
    }

    /// 单参数版本（new）
    func onChangeCompat<V: Equatable>(
        of value: V,
        initial: Bool = false,
        _ action: @escaping (V) -> Void
    ) -> some View {
        modifier(DYOnChangeCompatBox(value: value, initial: initial, action: { _, new in action(new) }))
    }

    /// 无参数版本：`{ doSomething() }`
    func onChangeCompat<V: Equatable>(
        of value: V,
        initial: Bool = false,
        _ action: @escaping () -> Void
    ) -> some View {
        modifier(DYOnChangeCompatBox(value: value, initial: initial, action: { _, _ in action() }))
    }
}

// MARK: - Scene 上的 onChange（WindowGroup 不是 View，需单独提供）

extension WindowGroup where Content: View {
    func onChangeCompat<V: Equatable>(of value: V, _ action: @escaping (V, V) -> Void) -> some Scene {
        self.onChange(of: value) { newValue in
            action(newValue, newValue)
        }
    }
}

// MARK: - iOS 27 的 toolbarVerticalEdge（低版本一律视为无竖栏）

extension EnvironmentValues {
    var toolbarVerticalEdge: HorizontalEdge? {
        get { nil }
        set { }
    }
}

// MARK: - NavigationStack -> NavigationView（强制 stack 样式，避免 iPad 分栏）

struct DYStack<Content: View>: View {
    private let content: Content

    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    var body: some View {
        NavigationView {
            content
        }
        .navigationViewStyle(.stack)
    }
}

// MARK: - Tab(value:) -> tabItem + tag

struct DYTabItem<V: Hashable, Content: View>: View {
    private let title: String
    private let systemImage: String
    private let value: V
    private let content: Content

    init(_ title: String, systemImage: String, value: V, @ViewBuilder content: () -> Content) {
        self.title = title
        self.systemImage = systemImage
        self.value = value
        self.content = content()
    }

    var body: some View {
        content
            .tabItem { Label(title, systemImage: systemImage) }
            .tag(value)
    }
}

// MARK: - ContentUnavailableView（iOS 17）兼容实现

struct DYContentUnavailableView<Actions: View>: View {
    private let title: String
    private let systemImage: String
    private let description: Text?
    private let actions: Actions

    init(_ title: String, systemImage: String) where Actions == EmptyView {
        self.title = title
        self.systemImage = systemImage
        self.description = nil
        self.actions = EmptyView()
    }

    init(_ title: String, systemImage: String, description: Text) where Actions == EmptyView {
        self.title = title
        self.systemImage = systemImage
        self.description = description
        self.actions = EmptyView()
    }

    init(
        _ title: String,
        systemImage: String,
        description: Text? = nil,
        @ViewBuilder actions: () -> Actions
    ) {
        self.title = title
        self.systemImage = systemImage
        self.description = description
        self.actions = actions()
    }

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: systemImage)
                .font(.system(size: 44, weight: .regular))
                .foregroundStyle(.secondary)
            Text(title)
                .font(.headline)
            if let description {
                description
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }
            actions
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - Mutex（iOS 18）兼容实现

final class DYMutex<T> {
    private let lock = NSLock()
    private var value: T

    init(_ value: T) {
        self.value = value
    }

    func withLock<R>(_ body: (inout T) throws -> R) rethrows -> R {
        lock.lock()
        defer { lock.unlock() }
        return try body(&value)
    }
}

// MARK: - GeometryProxy.reservedRegions（iOS 27）占位实现

enum DYReservedRegionKind {
    case division
    case occlusion
}

struct DYReservedRegion {
    var frame: CGRect = .zero
    var isActive: Bool = false
}

extension GeometryProxy {
    func reservedRegions(kind: DYReservedRegionKind) -> [DYReservedRegion] {
        []
    }
}

// MARK: - LabeledContent（iOS 16）兼容实现

struct DYLabeledContent<Label: View, Content: View>: View {
    private let label: Label
    private let content: Content

    init(@ViewBuilder content: () -> Content, @ViewBuilder label: () -> Label) {
        self.content = content()
        self.label = label()
    }

    init<S: StringProtocol, V>(_ title: S, value: V) where Label == Text, Content == Text {
        self.label = Text(String(title))
        self.content = Text(String(describing: value))
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            label
            Spacer(minLength: 8)
            content
        }
    }
}

// MARK: - AnyLayout（iOS 16）兼容实现

struct DYAnyLayoutSpec {
    var vertical: Bool
    var spacing: CGFloat

    func callAsFunction<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        DYAnyLayoutBody(vertical: vertical, spacing: spacing, content: content())
    }
}

struct DYAnyLayoutBody<Content: View>: View {
    let vertical: Bool
    let spacing: CGFloat
    let content: Content

    var body: some View {
        Group {
            if vertical {
                VStack(alignment: .leading, spacing: spacing) { content }
            } else {
                HStack(spacing: spacing) { content }
            }
        }
    }
}

// MARK: - 触感反馈（sensoryFeedback 替代）

enum DYHaptics {
    static func impact(_ style: UIImpactFeedbackGenerator.FeedbackStyle) {
        let g = UIImpactFeedbackGenerator(style: style)
        g.prepare()
        g.impactOccurred()
    }

    static func notify(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        let g = UINotificationFeedbackGenerator()
        g.prepare()
        g.notificationOccurred(type)
    }
}
