import React from "react";
import ReactDOM from "react-dom/client";
import "./index.css";
import WebTaskOrchestrator from "./WebTaskOrchestrator.jsx";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 32, fontFamily: "monospace", background: "#0f2020", color: "#f87171", minHeight: "100vh" }}>
          <h2 style={{ color: "#fbbf24", marginBottom: 12 }}>React Error</h2>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 13 }}>{this.state.error.toString()}</pre>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: 11, color: "#6ee7b7", marginTop: 12 }}>{this.state.error.stack}</pre>
          <button
            onClick={() => this.setState({ error: null })}
            style={{ marginTop: 20, padding: "8px 16px", background: "#0f766e", color: "white", border: "none", borderRadius: 6, cursor: "pointer" }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorBoundary>
      <WebTaskOrchestrator />
    </ErrorBoundary>
  </React.StrictMode>
);
