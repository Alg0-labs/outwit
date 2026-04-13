import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { authApi, agentApi, tokenStore, type AgentResponse, type UserData } from '../lib/api';
import { currentUser } from '../data/mockData';

interface AuthStore {
  user: UserData | null;
  agent: AgentResponse | null;
  isAuthenticated: boolean;
  isDemoMode: boolean;      // true when logged in with demo account (no real JWT)
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  sendOtp: (username: string, email: string, password: string) => Promise<void>;
  verifyOtp: (email: string, otp: string) => Promise<void>;
  demoLogin: () => void;
  logout: () => void;
  setAgent: (agent: AgentResponse) => void;
  loadAgent: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      agent: null,
      isAuthenticated: false,
      isDemoMode: false,
      isLoading: false,
      error: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
          const data = await authApi.login({ email, password });
          tokenStore.set(data.access_token);
          tokenStore.setRefresh(data.refresh_token);
          set({ user: data.user, isAuthenticated: true, isDemoMode: false, isLoading: false });
          // Eagerly load agent
          try {
            const me = await authApi.me();
            if (me.agent) set({ agent: me.agent as AgentResponse });
          } catch {}
        } catch (e: any) {
          set({ isLoading: false, error: e.detail ?? 'Login failed' });
          throw e;
        }
      },

      sendOtp: async (username, email, password) => {
        set({ isLoading: true, error: null });
        try {
          await authApi.sendOtp({ username, email, password });
          set({ isLoading: false });
        } catch (e: any) {
          set({ isLoading: false, error: e.detail ?? 'Failed to send OTP' });
          throw e;
        }
      },

      verifyOtp: async (email, otp) => {
        set({ isLoading: true, error: null });
        try {
          const data = await authApi.verifyOtp({ email, otp });
          tokenStore.set(data.access_token);
          tokenStore.setRefresh(data.refresh_token);
          set({ user: data.user, isAuthenticated: true, isDemoMode: false, isLoading: false });
        } catch (e: any) {
          set({ isLoading: false, error: e.detail ?? 'Invalid OTP' });
          throw e;
        }
      },

      demoLogin: () => {
        // Demo mode uses mock data — does not hit the backend
        set({
          user: {
            id: currentUser.id,
            username: currentUser.username,
            email: currentUser.email,
            login_streak: currentUser.loginStreak,
            is_verified: true,
            created_at: new Date().toISOString(),
          },
          agent: currentUser.agent
            ? {
                id: currentUser.agent.id,
                user_id: currentUser.id,
                name: currentUser.agent.name,
                avatar_id: currentUser.agent.avatar,
                color_theme: currentUser.agent.color,
                domain_expertise: currentUser.agent.expertise,
                reasoning_style: currentUser.agent.reasoningStyle,
                risk_profile: currentUser.agent.riskProfile,
                intel_balance: currentUser.agent.intelBalance,
                reputation_score: currentUser.agent.reputationScore,
                win_count: 0,
                loss_count: 0,
                current_streak: currentUser.agent.currentStreak,
                win_rate: currentUser.agent.winRate,
                total_predictions: currentUser.agent.totalPredictions,
                created_at: new Date().toISOString(),
              }
            : null,
          isAuthenticated: true,
          isDemoMode: true,
          isLoading: false,
          error: null,
        });
      },

      logout: () => {
        tokenStore.clear();
        set({ user: null, agent: null, isAuthenticated: false, isDemoMode: false, error: null });
      },

      setAgent: (agent) => set({ agent }),

      loadAgent: async () => {
        try {
          const agent = await agentApi.me();
          set({ agent });
        } catch {
          // Agent doesn't exist yet — that's fine
        }
      },

      clearError: () => set({ error: null }),
    }),
    {
      name: 'agent-arena-auth',
      // Don't persist error or loading state
      partialize: (state) => ({
        user: state.user,
        agent: state.agent,
        isAuthenticated: state.isAuthenticated,
        isDemoMode: state.isDemoMode,
      }),
    }
  )
);

// Listen for forced logout from API client (on unrecoverable 401)
if (typeof window !== 'undefined') {
  window.addEventListener('aa:logout', () => {
    useAuthStore.getState().logout();
  });
}
