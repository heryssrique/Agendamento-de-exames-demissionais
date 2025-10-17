import { useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function DepartmentSelection({ user, onUpdate }) {
  const [loading, setLoading] = useState(false);

  const selectDepartment = async (dept) => {
    setLoading(true);
    try {
      await axios.post(`${API}/auth/department`, { department: dept });
      onUpdate();
    } catch (error) {
      console.error("Failed to set department:", error);
      alert("Erro ao selecionar setor. Tente novamente.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="max-w-4xl w-full">
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <div className="text-center mb-8">
            <h1 className="text-3xl font-bold text-gray-900 mb-2">
              Bem-vindo, {user.name}!
            </h1>
            <p className="text-gray-600">
              Selecione seu setor para continuar
            </p>
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            <button
              onClick={() => selectDepartment("DP")}
              disabled={loading}
              data-testid="select-dp-button"
              className="group relative bg-gradient-to-br from-blue-500 to-blue-600 text-white p-8 rounded-xl hover:shadow-2xl transition-all transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-white/20 rounded-full mb-4">
                  <svg
                    className="w-8 h-8"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"
                    />
                  </svg>
                </div>
                <h3 className="text-2xl font-bold mb-2">Departamento Pessoal</h3>
                <p className="text-blue-100">
                  Criar e gerenciar solicitações de exames
                </p>
              </div>
            </button>

            <button
              onClick={() => selectDepartment("RH")}
              disabled={loading}
              data-testid="select-rh-button"
              className="group relative bg-gradient-to-br from-indigo-500 to-indigo-600 text-white p-8 rounded-xl hover:shadow-2xl transition-all transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="text-center">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-white/20 rounded-full mb-4">
                  <svg
                    className="w-8 h-8"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
                    />
                  </svg>
                </div>
                <h3 className="text-2xl font-bold mb-2">Recursos Humanos</h3>
                <p className="text-indigo-100">
                  Agendar exames e registrar resultados
                </p>
              </div>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default DepartmentSelection;
