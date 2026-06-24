import { create } from "zustand";
import axios from "axios";

export type UserRole = "super_admin" | "admin" | "user";

export interface AuthUser {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  team_id: string | null;
  team_name: string | null;
  is_active: boolean;
  last_login_at: string | null;
}

interface AuthState {
  user: AuthUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  isLoading: boolean;
  setAuth: (user: AuthUser, accessToken: string, refreshToken: string) => void;
  clearAuth: () => void;
  setLoading: (v: boolean) => void;
  loadFromStorage: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  refreshToken: null,
  isLoading: true,

  setAuth: (user, accessToken, refreshToken) => {
    localStorage.setItem("helios_jwt", accessToken);
    localStorage.setItem("helios_refresh", refreshToken);
    localStorage.setItem("helios_user_data", JSON.stringify(user));
    // Keep legacy flag for backward compatibility with existing AuthGate check
    localStorage.setItem("helios_auth", "1");
    localStorage.setItem("helios_user", user.email);
    set({ user, accessToken, refreshToken, isLoading: false });
  },

  clearAuth: () => {
    localStorage.removeItem("helios_jwt");
    localStorage.removeItem("helios_refresh");
    localStorage.removeItem("helios_user_data");
    localStorage.removeItem("helios_auth");
    localStorage.removeItem("helios_user");
    sessionStorage.removeItem("helios_auth");
    set({ user: null, accessToken: null, refreshToken: null, isLoading: false });
  },

  setLoading: (v) => set({ isLoading: v }),

  loadFromStorage: () => {
    const token = localStorage.getItem("helios_jwt");
    const userData = localStorage.getItem("helios_user_data");
    const refreshToken = localStorage.getItem("helios_refresh");
    if (token && userData) {
      try {
        const user = JSON.parse(userData) as AuthUser;
        set({ user, accessToken: token, refreshToken, isLoading: false });
        return;
      } catch {
        // corrupted — clear
      }
    }
    set({ isLoading: false });
  },
}));

// Role helpers
export const isAtLeast = (userRole: UserRole | undefined, minRole: UserRole): boolean => {
  const levels: Record<UserRole, number> = { user: 1, admin: 2, super_admin: 3 };
  return levels[userRole ?? "user"] >= levels[minRole];
};

export const ROLE_LABELS: Record<UserRole, string> = {
  super_admin: "Super Admin",
  admin: "Admin",
  user: "User",
};

export const ROLE_COLORS: Record<UserRole, string> = {
  super_admin: "text-red-400 bg-red-400/10 border-red-400/30",
  admin: "text-amber-400 bg-amber-400/10 border-amber-400/30",
  user: "text-cyan-400 bg-cyan-400/10 border-cyan-400/30",
};

// Axios interceptor — attach JWT to all API requests
export function setupAuthInterceptor(apiBaseUrl: string) {
  const instance = axios.create({ baseURL: apiBaseUrl });

  instance.interceptors.request.use((config) => {
    const token = localStorage.getItem("helios_jwt");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  instance.interceptors.response.use(
    (res) => res,
    async (err) => {
      if (err.response?.status === 401) {
        const refreshToken = localStorage.getItem("helios_refresh");
        if (refreshToken) {
          try {
            const res = await axios.post(`${apiBaseUrl}/auth/refresh`, { refresh_token: refreshToken });
            const { access_token, refresh_token: newRefresh, user } = res.data;
            useAuthStore.getState().setAuth(user, access_token, newRefresh);
            err.config.headers.Authorization = `Bearer ${access_token}`;
            return instance.request(err.config);
          } catch {
            useAuthStore.getState().clearAuth();
            window.location.href = "/login";
          }
        } else {
          useAuthStore.getState().clearAuth();
          window.location.href = "/login";
        }
      }
      return Promise.reject(err);
    }
  );

  return instance;
}
