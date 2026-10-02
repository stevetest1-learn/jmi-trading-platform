import { useState } from "react";
import { useAuth } from "../state/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await login(username, password);
    } catch {
      setError("Invalid username or password");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page">
      <form className="login-card" onSubmit={handleSubmit}>
        <div className="login-card__logo">JMI</div>
        <h1>JMI Crypto Trading GUI</h1>
        <input
          type="text"
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button type="submit" className="btn btn--primary" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
        {error && <div className="login-card__error">{error}</div>}
        <p className="login-card__hint">Demo accounts: alice / bob / market_maker — password demo1234</p>
      </form>
    </div>
  );
}
