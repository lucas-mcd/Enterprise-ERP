export type Source = "real" | "demo";
export type EntryKind = "receita" | "despesa";
export type EntryStatus = "pendente" | "concluido" | "aguardando_aprovacao";
export type Entry = {
  id: string;
  description: string;
  counterparty: string;
  category: string;
  kind: EntryKind;
  status: EntryStatus;
  amount: string;
  currency: string;
  due_date: string;
  settled_on: string | null;
  effective_on: string;
  is_simulated: boolean;
  version: number;
  cost_center_id?: string | null;
};
export type EntryInput = Pick<
  Entry,
  | "description"
  | "counterparty"
  | "category"
  | "kind"
  | "status"
  | "amount"
  | "due_date"
  | "settled_on"
  | "cost_center_id"
>;
export type Filters = {
  sort?: string;
  desc?: string;
  source: Source;
  start_date: string;
  end_date: string;
  q: string;
  status: string;
  kind: string;
  category: string;
};
export type EntryPage = {
  items: Entry[];
  total: number;
  page: number;
  page_size: number;
};
export type CashPoint = {
  day: string;
  income: string;
  expense: string;
  pending_income: string;
  pending_expense: string;
};
export type Summary = {
  source: Source;
  total_records: number;
  income: string;
  expense: string;
  net: string;
  pending_income: string;
  pending_expense: string;
  points: CashPoint[];
  expense_categories: { category: string; amount: string }[];
};
export const categories = [
  "Vendas",
  "Serviços",
  "Assinaturas",
  "Fornecedores",
  "Pessoal",
  "Marketing",
  "Infraestrutura",
  "Impostos",
  "Outros",
];
