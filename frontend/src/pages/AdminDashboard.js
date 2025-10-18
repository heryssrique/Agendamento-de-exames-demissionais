import { useState, useEffect } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function AdminDashboard({ user, onLogout }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [adminEmails, setAdminEmails] = useState([]);
  const [loadingAdmins, setLoadingAdmins] = useState(false);
  const [history, setHistory] = useState({ items: [], loading: false, error: null });
  const [historyFilters, setHistoryFilters] = useState({ exam_id: "", actor_email: "", limit: 200 });

  useEffect(() => {
    fetchUsers();
    fetchAdminEmails();
    fetchHistory();
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

  const fetchHistory = async () => {
    try {
      setHistory((prev) => ({ ...prev, loading: true, error: null }));
      const params = new URLSearchParams();
      if (historyFilters.exam_id) params.append("exam_id", historyFilters.exam_id);
      if (historyFilters.actor_email) params.append("actor_email", historyFilters.actor_email);
      if (historyFilters.limit) params.append("limit", historyFilters.limit);
      const res = await axios.get(`${API}/admin/history?${params.toString()}`);
      setHistory({ items: res.data || [], loading: false, error: null });
    } catch (error) {
      console.error("Error fetching history:", error);
      setHistory({ items: [], loading: false, error: "Falha ao carregar histórico" });
    }
  };

  const fetchAdminEmails = async () => {
    try {
      setLoadingAdmins(true);
      const res = await axios.get(`${API}/auth/admin-emails`);
      setAdminEmails(res.data.admin_emails || []);
    } catch (error) {
      console.error("Error fetching admin emails:", error);
      setAdminEmails([]);
      if (error.response?.status === 403) {
        alert("❌ Permissão negada para listar e-mails de administradores.");
      }
    } finally {
      setLoadingAdmins(false);
    }
  };

  const impersonate = async (dept) => {
    try {
      await axios.post(`${API}/auth/impersonate-department`, { department: dept });
      window.location.href = "/";
    } catch (error) {
      console.error("Error starting impersonation:", error);
      alert("❌ Não foi possível entrar como setor. Tente novamente.");
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

  const deleteUser = async (userId, userEmail) => {
    if (user && user.id === userId) {
      alert("❌ Você não pode excluir seu próprio usuário.");
      return;
    }
    if (!window.confirm(`Tem certeza que deseja excluir o usuário ${userEmail}? Esta ação é irreversível.`)) {
      return;
    }
    try {
      await axios.delete(`${API}/admin/users/${userId}`);
      alert("✅ Usuário excluído com sucesso!");
      fetchUsers();
    } catch (error) {
      console.error("Error deleting user:", error);
      const msg = error.response?.data?.detail || "Erro ao excluir usuário.";
      alert(`❌ ${msg}`);
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

  const getEventLabel = (event) => {
    const map = {
      CREATED: 'Criado',
      UPDATED: 'Atualizado',
      DELETED: 'Excluído',
    };
    return map[event] || event;
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
            <div className="flex items-center gap-3">
              <button
                onClick={() => impersonate("DP")}
                className="text-blue-600 hover:text-blue-900 font-medium"
                data-testid="impersonate-dp"
              >
                Entrar como DP
              </button>
              <button
                onClick={() => impersonate("RH")}
                className="text-indigo-600 hover:text-indigo-900 font-medium"
                data-testid="impersonate-rh"
              >
                Entrar como RH
              </button>
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
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Admin Emails */}
        <div className="mb-6 bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900">E-mails de Administradores (CONFIG)</h2>
              <p className="text-gray-600 text-sm">Lista proveniente de ADMIN_EMAILS (arquivo .env)</p>
            </div>
            <button
              onClick={fetchAdminEmails}
              className="text-purple-600 hover:text-purple-900 font-medium"
              data-testid="refresh-admin-emails"
            >
              Atualizar
            </button>
          </div>
          {loadingAdmins ? (
            <div className="text-gray-600">Carregando...</div>
          ) : adminEmails.length === 0 ? (
            <div className="text-gray-600">Nenhum e-mail configurado.</div>
          ) : (
            <ul className="list-disc pl-6 space-y-1" data-testid="admin-email-list">
              {adminEmails.map((e) => (
                <li key={e} className="text-gray-800">{e}</li>
              ))}
            </ul>
          )}
        </div>

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
                        <button
                          onClick={() => deleteUser(u.id, u.email)}
                          className={`font-medium ml-2 ${user && user.id === u.id ? 'text-gray-400 cursor-not-allowed' : 'text-red-600 hover:text-red-900'}`}
                          title={user && user.id === u.id ? 'Você não pode excluir seu próprio usuário' : 'Excluir usuário'}
                          disabled={user && user.id === u.id}
                          data-testid={`delete-user-${u.id}`}
                        >
                          Excluir
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {/* History */}
        <div className="mb-6 bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-bold text-gray-900">Histórico de Eventos</h2>
              <p className="text-gray-600 text-sm">Criações e alterações de exames</p>
            </div>
            <button onClick={fetchHistory} className="text-purple-600 hover:text-purple-900 font-medium" data-testid="refresh-history">
              Atualizar
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
            <input
              type="text"
              placeholder="Filtrar por Exam ID"
              value={historyFilters.exam_id}
              onChange={(e) => setHistoryFilters({ ...historyFilters, exam_id: e.target.value })}
              className="px-3 py-2 border border-gray-300 rounded-lg"
            />
            <input
              type="email"
              placeholder="Filtrar por e-mail do autor"
              value={historyFilters.actor_email}
              onChange={(e) => setHistoryFilters({ ...historyFilters, actor_email: e.target.value })}
              className="px-3 py-2 border border-gray-300 rounded-lg"
            />
            <select
              value={historyFilters.limit}
              onChange={(e) => setHistoryFilters({ ...historyFilters, limit: Number(e.target.value) })}
              className="px-3 py-2 border border-gray-300 rounded-lg"
            >
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
              <option value={500}>500</option>
            </select>
          </div>

          <div className="mb-4">
            <button onClick={fetchHistory} className="px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700" data-testid="apply-filters">
              Aplicar filtros
            </button>
          </div>

          {history.loading ? (
            <div className="text-gray-600">Carregando...</div>
          ) : history.error ? (
            <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg">{history.error}</div>
          ) : history.items.length === 0 ? (
            <div className="text-gray-600">Nenhum evento encontrado.</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Data</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Evento</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Exam ID</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Autor</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Setor</th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Detalhes</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200" data-testid="history-table-body">
                  {history.items.map((h) => (
                    <tr key={h.id}>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{new Date(h.timestamp).toLocaleString("pt-BR")}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{getEventLabel(h.event)}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">{(h.payload && h.payload.nome) || h.nome || h.exam_id}</td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">{h.actor_email}</td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className="px-2 py-1 text-xs rounded-full bg-purple-100 text-purple-800">{h.actor_department || "-"}</span>
                      </td>
                      <td className="px-6 py-4 whitespace-pre-wrap text-xs text-gray-600">
                        {h.event === 'UPDATED' ? (
                          <div>
                            <div><strong>Status:</strong> {h.old_status} → {h.new_status}</div>
                          </div>
                        ) : (
                          <div className="text-gray-500">-</div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AdminDashboard;
