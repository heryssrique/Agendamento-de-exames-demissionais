import { useState, useEffect } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function AdminDashboard({ user, onLogout }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await axios.get(`${API}/admin/users`);
      setUsers(response.data);
    } catch (error) {
      console.error("Error fetching users:", error);
      alert("Erro ao carregar usuários. Verifique suas permissões.");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await axios.post(`${API}/auth/logout`);
      window.location.href = "/";
    } catch (error) {
      console.error("Logout error:", error);
    }
  };

  const changeDepartment = async (userId, newDepartment) => {
    if (!window.confirm(`Alterar usuário para ${newDepartment}?`)) {
      return;
    }

    try {
      await axios.patch(`${API}/admin/users/${userId}`, {
        department: newDepartment,
      });
      alert("✅ Departamento alterado com sucesso!");
      fetchUsers();
    } catch (error) {
      console.error("Error changing department:", error);
      alert("❌ Erro ao alterar departamento.");
    }
  };

  const getDepartmentBadge = (dept) => {
    const badges = {
      DP: "bg-blue-100 text-blue-800",
      RH: "bg-indigo-100 text-indigo-800",
      ADMIN: "bg-purple-100 text-purple-800",
    };
    return badges[dept] || "bg-gray-100 text-gray-800";
  };

  const getDepartmentLabel = (dept) => {
    const labels = {
      DP: "Departamento Pessoal",
      RH: "Recursos Humanos",
      ADMIN: "Administrador",
    };
    return labels[dept] || dept || "Sem Setor";
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white shadow">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-600 rounded-lg flex items-center justify-center">
                <svg
                  className="w-6 h-6 text-white"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                  />
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-gray-900">
                  Painel de Administração
                </h1>
                <p className="text-sm text-gray-600">{user.name}</p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              data-testid="logout-button"
              className="text-gray-600 hover:text-gray-900 font-medium"
            >
              Sair
            </button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900">
            Gerenciamento de Usuários
          </h2>
          <p className="text-gray-600 mt-1">
            Altere o departamento dos usuários do sistema
          </p>
        </div>

        {/* Users List */}
        {loading ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mx-auto"></div>
          </div>
        ) : users.length === 0 ? (
          <div className="bg-white rounded-lg shadow p-12 text-center">
            <svg
              className="w-16 h-16 text-gray-400 mx-auto mb-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"
              />
            </svg>
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              Nenhum usuário cadastrado
            </h3>
          </div>
        ) : (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Usuário
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Email
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Setor Atual
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Ações
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {users.map((u) => (
                    <tr key={u.id} data-testid={`user-row-${u.id}`}>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          {u.picture && (
                            <img
                              src={u.picture}
                              alt={u.name}
                              className="w-10 h-10 rounded-full mr-3"
                            />
                          )}
                          <div className="text-sm font-medium text-gray-900">
                            {u.name}
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {u.email}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`px-3 py-1 inline-flex text-xs leading-5 font-semibold rounded-full ${getDepartmentBadge(
                            u.department
                          )}`}
                        >
                          {getDepartmentLabel(u.department)}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm space-x-2">
                        {u.department !== "DP" && (
                          <button
                            onClick={() => changeDepartment(u.id, "DP")}
                            className="text-blue-600 hover:text-blue-900 font-medium"
                            data-testid={`change-to-dp-${u.id}`}
                          >
                            → DP
                          </button>
                        )}
                        {u.department !== "RH" && (
                          <button
                            onClick={() => changeDepartment(u.id, "RH")}
                            className="text-indigo-600 hover:text-indigo-900 font-medium"
                            data-testid={`change-to-rh-${u.id}`}
                          >
                            → RH
                          </button>
                        )}
                        {u.department !== "ADMIN" && (
                          <button
                            onClick={() => changeDepartment(u.id, "ADMIN")}
                            className="text-purple-600 hover:text-purple-900 font-medium"
                            data-testid={`change-to-admin-${u.id}`}
                          >
                            → Admin
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AdminDashboard;
