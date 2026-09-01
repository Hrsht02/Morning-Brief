export default function SandboxCheck({ check }) {
  return (
    <div style={{ padding: "9px 0", borderBottom: "1px solid var(--border)" }}>
      <strong>{check.passed ? "✓" : "✕"} {check.name}</strong>
      <div style={{ color: "var(--ink-faint)", fontSize: 12.5 }}>{check.detail}</div>
    </div>
  );
}
