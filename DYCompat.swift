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

struct DYTab<V: Hashable, Content: View>: View {
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

// MARK: - AnyLayout（iOS 16）兼容实现：仅支持水平/垂直切换

struct DYAnyLayout: Layout {
    var horizontal: Bool

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        DYAnyLayout.measure(horizontal: horizontal, proposal: proposal, subviews: subviews)
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        let count = max(subviews.count, 1)
        if horizontal {
            let w = bounds.width / CGFloat(count)
            for (i, sub) in subviews.enumerated() {
                sub.place(
                    at: CGPoint(x: bounds.minX + w * CGFloat(i), y: bounds.minY),
                    proposal: ProposedViewSize(width: w, height: bounds.height)
                )
            }
        } else {
            let h = bounds.height / CGFloat(count)
            for (i, sub) in subviews.enumerated() {
                sub.place(
                    at: CGPoint(x: bounds.minX, y: bounds.minY + h * CGFloat(i)),
                    proposal: ProposedViewSize(width: bounds.width, height: h)
                )
            }
        }
    }

    static func measure(horizontal: Bool, proposal: ProposedViewSize, subviews: Subviews) -> CGSize {
        var w: CGFloat = 0
        var h: CGFloat = 0
        for sub in subviews {
            let s = sub.sizeThatFits(.unspecified)
            if horizontal {
                w += s.width
                h = max(h, s.height)
            } else {
                h += s.height
                w = max(w, s.width)
            }
        }
        return CGSize(
            width: proposal.width ?? w,
            height: proposal.height ?? h
        )
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
