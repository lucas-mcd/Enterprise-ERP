import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFile } from "node:fs/promises";

const tenant = process.env.ERP_TRAINING_TENANT;
const password = process.env.ERP_TEST_PASSWORD;
async function login(page: Page, email: string) {
  if (!tenant || !password)
    throw new Error(
      "Prepare uma empresa descartável com ERP_TRAINING_TENANT e ERP_TEST_PASSWORD.",
    );
  await page.goto("/");
  await page.getByText("Configuração da empresa").click();
  await page.getByLabel("Identificador da empresa").fill(tenant);
  await page.getByLabel("Email corporativo").fill(email);
  await page.getByLabel("Senha", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Entrar na plataforma" }).click();
  await expect(page).toHaveURL(/\/app/);
}
async function capture(page: Page, name: string) {
  if (process.env.ERP_CAPTURE === "1")
    await page.screenshot({ path: `../docs/imagens/${name}.png` });
}

test("venda de R$ 600, estoque, baixa e PDF com perfis comercial e financeiro", async ({
  page,
}) => {
  await login(page, "vendedor@enterprise.com");
  await page.goto("/app/vendas?source=real&tab=crm");
  const blocked = page
    .locator("article")
    .filter({ hasText: "Pedido acima do limite" });
  await blocked.getByRole("button", { name: "Converter em pedido" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: /crédito insuficiente/i }),
  ).toBeVisible();
  const sale = page.locator("article").filter({ hasText: "Reposição Aurora" });
  await sale.getByRole("button", { name: "Converter em pedido" }).click();
  const open = sale.getByRole("link", { name: /Abrir pedido/ });
  await expect(open).toBeVisible();
  await capture(page, "funil");
  await open.click();
  await page.getByRole("button", { name: "Concluir", exact: true }).click();
  await page.getByRole("button", { name: "Confirmar operação" }).click();
  await expect(
    page.getByText("Financeiro vinculado", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByText("Itens do pedido", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Abrir lançamento financeiro" }),
  ).toHaveCount(0);
  await capture(page, "pedido");
  await page.getByRole("link", { name: "Ver estoque" }).click();
  const product = page.getByRole("row").filter({ hasText: "AUR-KIT" });
  await expect(
    product.getByRole("cell", { name: "7", exact: true }),
  ).toBeVisible();
  await product.getByRole("button", { name: /Ver \/ movimentar/ }).click();
  await expect(page.getByText(/^Venda concluída ·/)).toBeVisible();
  await page.goto("/app/financeiro?source=real");
  await expect(
    page.getByText("Seu perfil não possui acesso ao Financeiro."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sair da conta" }).click();
  await expect(
    page.getByRole("button", { name: "Entrar na plataforma" }),
  ).toBeVisible();

  await login(page, "financeiro@enterprise.com");
  await page.goto("/app/financeiro?source=real&tab=bank");
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Baixar extrato de exemplo" }).click();
  const path = await (await downloaded).path();
  await page.getByLabel("Arquivo de extrato JSON").setInputFiles({
    name: "treinamento.json",
    mimeType: "application/json",
    buffer: await readFile(path!),
  });
  await page.getByRole("button", { name: "Confirmar importação" }).click();
  await page.getByRole("button", { name: "Revisar candidatos" }).click();
  const dialog = page.getByRole("dialog", { name: "Revisar conciliação" });
  await expect(dialog.getByText(/Venda [0-9a-f]{8}/)).toBeVisible();
  await capture(page, "conciliacao");
  await dialog.getByRole("button", { name: "Confirmar", exact: true }).click();
  await expect(page.getByText("Conciliado", { exact: true })).toBeVisible();
  const a11y = await new AxeBuilder({ page })
    .withRules(["button-name", "label", "link-name", "document-title"])
    .analyze();
  expect(a11y.violations).toEqual([]);
  await page
    .getByRole("button", { name: "Fluxo de caixa", exact: true })
    .click();
  const receipt = page
    .getByRole("row")
    .filter({ hasText: /Venda [0-9a-f]{8}/ });
  await expect(receipt).toContainText(/600,00/);
  await page.getByRole("button", { name: "Exportar relatório PDF" }).click();
  await page.reload();
  await page.getByRole("button", { name: "Meus relatórios" }).click();
  const pdf = page.getByRole("button", { name: "Baixar PDF", exact: true });
  await expect(pdf).toBeVisible({ timeout: 60000 });
  const pdfDownload = page.waitForEvent("download");
  await pdf.click();
  const file = await (await pdfDownload).path();
  expect((await readFile(file!)).subarray(0, 5).toString()).toBe("%PDF-");
});
