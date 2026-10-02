import "./App.css";
import { LoginPage } from "./pages/LoginPage";
import { TradingPage } from "./pages/TradingPage";
import { AuthProvider, useAuth } from "./state/AuthContext";

function AppShell() {
  const { token, ready } = useAuth();
  if (!ready) return null;
  return token ? <TradingPage /> : <LoginPage />;
}

function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  );
}

export default App;
