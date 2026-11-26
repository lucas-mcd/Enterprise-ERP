# Enterprise ERP

ERP de portfólio para uma distribuidora fictícia. O projeto acompanha uma venda desde a negociação com o cliente até a saída dos produtos do estoque e a confirmação do pagamento.

![Funil de vendas do ERP]

## Como rodar

Você precisa do **Docker Desktop** em execução. Baixe ou clone o projeto e abra o terminal na pasta que contém o arquivo `docker-compose.yml`.

### 1. Configure o ambiente

Na primeira instalação, copie `.env.example` para `.env`.

**Windows**
```cmd
copy .env.example .env
```

**Linux ou macOS**
```bash
cp .env.example .env
```

Abra o `.env` em um editor e substitua os valores de exemplo:

- `POSTGRES_PASSWORD` — escolha uma senha alfanumérica para o banco.
- `JWT_SECRET` — use um segredo aleatório de pelo menos 32 caracteres.

Se você já tem um `.env` da versão anterior, preserve o arquivo e siga o [guia de atualização]

### 2. Inicie o sistema

```bash
docker compose up -d --build --wait
```

Quando o comando terminar, abra **[http://localhost:8080](http://localhost:8080)**.

### 3. Crie as contas e faça o primeiro login

Execute no terminal:

```bash
docker compose exec api python -m erp.shared.infrastructure.database.seed --training
```

O comando cria uma empresa fictícia e três usuários. Os e-mails já estão definidos. Quando o terminal mostrar cada e-mail, escolha uma senha de **14 a 128 caracteres** para aquela conta. É normal a senha ficar invisível enquanto você digita. Pressione Enter para confirmar.

| Perfil | E-mail de acesso |
| --- | --- |
| Administrador | `admin@enterprise.com` |
| Financeiro | `financeiro@enterprise.com` |
| Vendedor | `vendedor@enterprise.com` |

Ao terminar, o terminal mostra um `tenant_id`. Copie esse identificador e guarde as senhas que escolheu.

**Para testar sua primeira venda:**

1. Abra [http://localhost:8080](http://localhost:8080).
2. Clique em **Configuração da empresa** e cole o `tenant_id`.
3. Entre com `vendedor@enterprise.com` e a senha que você criou para o vendedor.

Para testar o financeiro, saia da conta e entre com `financeiro@enterprise.com`, usando a senha desse perfil e o mesmo `tenant_id`.

Nos próximos acessos, use essas mesmas credenciais. Rode `--training` novamente apenas se quiser criar outra empresa para recomeçar a demonstração.

## Uma venda para testar

A empresa de treinamento começa com **10 kits em estoque** e uma oportunidade chamada **Reposição Aurora**.

1. Entre como **vendedor**. Em **Vendas → Clientes & CRM**, selecione **Operação real**. Essa opção permite editar os dados fictícios do treinamento.
2. Abra **Reposição Aurora** e converta a oportunidade em pedido. São **3 kits a R$ 200**, com verificação do limite de crédito do cliente.
3. Clique em **Abrir pedido** e conclua a venda. No histórico do produto, confira a saída de 3 unidades e o saldo de **7 kits**. O ERP também gera uma conta de **R$ 600 a receber**.
4. Entre como **financeiro**, usando o mesmo `tenant_id`. Em **Financeiro → Conciliação bancária**, selecione **Operação real**, baixe o extrato de exemplo e importe o arquivo. Confira os R$ 600 e confirme o recebimento.

Para experimentar uma regra de negócio, tente converter a oportunidade **Pedido acima do limite**. O ERP informa o motivo do bloqueio e mantém a negociação no funil.

## O que tem no projeto

Além do fluxo de vendas, o sistema reúne compras e fornecedores, movimentações de estoque, contas a pagar e a receber, centros de custo, aprovações e relatórios em PDF, CSV e Excel. Cada perfil tem suas permissões, e as alterações ficam registradas na auditoria.

A interface usa **React e TypeScript**. A API usa **FastAPI, SQLAlchemy e PostgreSQL**. Ao concluir uma venda, a baixa de estoque e a criação do recebível acontecem na mesma transação. Os relatórios em PDF são processados em segundo plano com **Celery e Redis** e ficam disponíveis em **Meus relatórios**.

Os testes usam **Pytest, Vitest e Playwright**. O teste de navegador reproduz a venda acima com os perfis comercial e financeiro, da conversão da oportunidade até o download do PDF.
