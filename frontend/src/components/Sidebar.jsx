import React from "react";
import { NavLink } from "react-router-dom";

const NAV_ITEMS = [
  { to: "/reconciliation", label: "EOD Reconciliation" },
  { to: "/analytics", label: "Analytics" },
  { to: "/narrative", label: "AI Narrative Summary" },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">SwasthiQ</div>
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `sidebar-item${isActive ? " active" : ""}`}
          >
            <span className="dot" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
