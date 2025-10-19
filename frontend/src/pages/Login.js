import { useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const AUTH_URL = "https://auth.emergentagent.com";

function Login({ onLogin }) {
  const [processing, setProcessing] = useState(false);

  useEffect(() => {
    // Check for session_id in URL fragment
    const fragment = window.location.hash;
    if (fragment && fragment.includes("session_id=")) {
      const sessionId = fragment.split("session_id=")[1].split("&")[0];
      processSessionId(sessionId);
    }
  }, []);

  const processSessionId = async (sessionId) => {
    setProcessing(true);
    try {
      console.log("Processing session_id...");
      const response = await axios.post(
        `${API}/auth/session`,
        {},
        {
          headers: { "X-Session-ID": sessionId },
          withCredentials: true
        }
      );
      
      console.log("Session created:", response.data);
      
      // Clean URL fragment
      window.history.replaceState(null, "", window.location.pathname);
      
      // Reload to check auth
      onLogin();
    } catch (error) {
      console.error("Authentication failed:", error);
      console.error("Error details:", error.response?.data);
      alert("Falha na autenticação. Por favor, tente novamente.");
      setProcessing(false);
    }
  };

  const handleGoogleLogin = () => {
    const redirectUrl = encodeURIComponent(window.location.origin);
    window.location.href = `${AUTH_URL}/?redirect=${redirectUrl}`;
  };

  if (processing) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-xl p-8 text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Processando autenticação...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-full mb-4">
              <svg
                className="w-8 h-8 text-white"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              Gerenciador de Exames
            </h1>
            <p className="text-gray-600">
              Sistema de agendamento de exames demissionais
            </p>
          </div>

          <button
            onClick={handleGoogleLogin}
            data-testid="google-login-button"
            className="w-full bg-white border-2 border-gray-300 text-gray-700 py-3 px-4 rounded-lg font-medium hover:bg-gray-50 transition-colors flex items-center justify-center gap-3 group"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            <span>Entrar com Google</span>
          </button>

          <div className="mt-6 text-center text-sm text-gray-500">
            <p>Acesso exclusivo para DP e RH</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;
