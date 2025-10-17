import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import axios from "axios";
import Login from "./pages/Login";
import DepartmentSelection from "./pages/DepartmentSelection";
import DPDashboard from "./pages/DPDashboard";
import RHDashboard from "./pages/RHDashboard";
import AdminDashboard from "./pages/AdminDashboard";
import "@/App.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

axios.defaults.withCredentials = true;

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      const response = await axios.get(`${API}/auth/me`);
      setUser(response.data);
    } catch (error) {
      console.error("Not authenticated");
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto"></div>
          <p className="mt-4 text-gray-600">Carregando...</p>
        </div>
      </div>
    );
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            !user ? (
              <Login onLogin={checkAuth} />
            ) : !user.department ? (
              <DepartmentSelection user={user} onUpdate={checkAuth} />
            ) : user.department === "DP" ? (
              <Navigate to="/dp/dashboard" replace />
            ) : user.department === "RH" ? (
              <Navigate to="/rh/dashboard" replace />
            ) : user.department === "ADMIN" ? (
              <Navigate to="/admin/dashboard" replace />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/dp/dashboard"
          element={
            user && user.department === "DP" ? (
              <DPDashboard user={user} onLogout={checkAuth} />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/rh/dashboard"
          element={
            user && user.department === "RH" ? (
              <RHDashboard user={user} onLogout={checkAuth} />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
        <Route
          path="/admin/dashboard"
          element={
            user && user.department === "ADMIN" ? (
              <AdminDashboard user={user} onLogout={checkAuth} />
            ) : (
              <Navigate to="/" replace />
            )
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
