import type { components } from "../../../shared/api/generated";
export type User = components["schemas"]["UserResponse"];
export type Session = { token: string; user: User; expiresAt: number };
export type LoginInput = components["schemas"]["LoginRequest"];
export type LoginResult = components["schemas"]["LoginResponse"];
export type Dashboard = {
  tenant_name: string;
  is_simulated: boolean;
  total_records: number;
  completed: number;
  total_amount: string;
  activities: {
    code: string;
    category: string;
    description: string;
    status: string;
    amount: string;
  }[];
  audit: {
    id: string;
    table: string;
    operation: string;
    occurred_at: string;
  }[];
};
