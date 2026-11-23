const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

test("carregar exibe os valores da API como texto literal", async () => {
  const texto = '<strong data-teste="1">Texto & dados</strong>';
  const esperado = "&lt;strong data-teste=&quot;1&quot;&gt;Texto &amp; dados&lt;/strong&gt;";
  const respostas = {
    "/auth/eu": { id: 1, perfil: "tecnico", nome: "Carla" },
    "/usuarios": [{ id: 1, perfil: "tecnico", nome: texto }],
    "/ativos": [{ id: 1, patrimonio: "PC-01", descricao: texto }],
    "/chamados": [{
      id: 1, solicitante_id: 1, titulo: texto, prioridade: "alta", status: "aberto",
      tecnico_id: null, prazo_sla: "2026-01-01T08:00:00",
    }],
    "/chamados/painel": { total: 1, por_status: { aberto: 1 }, atrasados: 0 },
    "/notificacoes": [{ tipo: "ChamadoAberto", mensagem: texto, criada_em: "2026-01-01T00:00:00" }],
  };
  const elementos = new Map();
  const contexto = vm.createContext({
    document: {
      getElementById(id) {
        if (!elementos.has(id)) elementos.set(id, { value: "", addEventListener() {} });
        return elementos.get(id);
      },
    },
    sessionStorage: { getItem: () => null },
    fetch: async (url) => {
      assert.ok(url in respostas, url);
      return { ok: true, status: 200, json: async () => respostas[url] };
    },
  });
  const script = fs.readFileSync(path.join(__dirname, "../app/web/app.js"), "utf8");
  vm.runInContext(script, contexto);
  await vm.runInContext("token = 'token-de-teste'; carregar()", contexto);

  for (const id of ["lista", "ativo", "avisos"]) {
    const html = elementos.get(id).innerHTML;
    assert.ok(html.includes(esperado), id);
    assert.ok(!html.includes("<strong"), id);
  }
});
