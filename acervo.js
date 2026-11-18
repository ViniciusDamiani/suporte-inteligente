/* Reutiliza a autenticação e o cliente HTTP existentes. Nenhuma chave de IA no navegador. */
function initKnowledgeSearch({
  form = $("#knowledge-form"), input = $("#knowledge-query"),
  results = $("#knowledge-results"), submit = $("#knowledge-submit"),
  beforeSearch = () => {},
  onReset = () => {},
} = {}) {
  if (!session.token) { location.replace("index.html"); return; }
  const error = $("#knowledge-error");
  let busy = false, lastRequest = null, conversationId = null, pendingRequest = null, conversationClosed = false;
  let currentOptions = [];
  let retryMessage = "";
  const technicalFailures = {
    rejected: "Encontrei casos relacionados, mas não consegui validar a resposta gerada. Você pode tentar novamente com a mesma pergunta.",
    unavailable: "Não consegui concluir a resposta porque o serviço de IA está indisponível. Tente novamente em instantes.",
    rate_limited: "O serviço de IA atingiu o limite de uso. Aguarde antes de tentar novamente.",
    busy: "O assistente está atendendo outras consultas. Tente novamente em instantes.",
    disabled: "O assistente está desativado. Você pode usar a pesquisa sem IA.",
    not_configured: "O assistente precisa ser configurado no servidor. Você pode usar a pesquisa sem IA.",
    budget_exceeded: "Esta consulta ultrapassou o limite de contexto do assistente. Inicie uma investigação mais específica.",
  };
  const transcript = $("#knowledge-conversation"), reset = $("#knowledge-reset"), local = $("#knowledge-local");
  const chatView = form.closest?.(".stage, .knowledge-main");
  const initialPlaceholder = input.placeholder;
  function controls(locked) {
    busy = locked;
    submit.disabled = locked;
    if (reset) reset.disabled = locked;
    if (local) local.disabled = locked;
    input.disabled = locked;
    transcript?.querySelectorAll?.("[data-option], [data-other], [data-retry]").forEach(button => { button.disabled = locked; });
  }
  function resetConversation() {
    if (busy) return;
    conversationId = null; pendingRequest = null; conversationClosed = false; lastRequest = null;
    currentOptions = [];
    retryMessage = "";
    if (transcript) transcript.innerHTML = "";
    chatView?.classList.remove("has-conversation");
    results.innerHTML = ""; error.textContent = ""; input.value = "";
    input.placeholder = initialPlaceholder; input.dispatchEvent(new Event("input")); input.focus();
    onReset();
  }
  if (reset) reset.onclick = resetConversation;
  const usages = {
    hipotese_para_investigacao: "Hipótese para investigação",
    contexto_historico: "Contexto histórico",
    acao_historica_condicionada: "Ação histórica — conferir condições",
    resultado_historico_condicionado: "Resultado histórico — conferir condições",
  };
  const policy = (metadata) => `<p class="knowledge-policy">${esc(usages[metadata.uso_na_recomendacao] || "Conteúdo sujeito a revisão técnica")}. A pertinência para esta ocorrência precisa ser verificada.</p>`;
  const reference = (item) => `<p class="knowledge-reference">Fonte: ${esc(item.source_id)}<br>Pacote: ${esc(item.package_id)}<br>Registro: ${esc(item.origin.registro_id || item.source_id)}<br>Arquivo de origem: ${esc(item.origin.arquivo_relativo || "não informado")}</p>`;
  if ($("#knowledge-logout")) $("#knowledge-logout").onclick = logout;
  $("#knowledge-close").onclick = () => $("#knowledge-document").close();
  const userMessage = text => `<article class="knowledge-message user" aria-label="Sua mensagem"><p>${esc(text)}</p></article>`;
  const assistantMessage = content => `<article class="knowledge-message assistant" aria-label="Resposta do assistente">${content}</article>`;
  const answerText = answer => answer.paragraphs.map(p => `<p class="knowledge-answer-text">${esc(p.text)}</p>`).join("");
  function render(data) {
    const notice = data.warnings.filter(w => !technicalFailures[data.generation_status]
      && !(data.decision === "ask" && w.startsWith("Preciso entender o sintoma")))
      .map(w => `<p class="knowledge-status">${esc(w)}</p>`).join("");
    const answer = data.generated_answer;
    // As citações já foram validadas no servidor. Só elas definem as fontes finais.
    const byKey = new Map(data.results.map(ticket => [ticket.document_key, ticket]));
    const citedKeys = answer ? [...new Set(answer.paragraphs.flatMap(p => p.citations.map(c => c.document_key)))] : [];
    const usedSources = citedKeys.map(key => byKey.get(key)).filter(Boolean);
    const usedTickets = [...new Map(usedSources.map(ticket => [
      `${ticket.package_id || ""}:${ticket.ticket_reference || ticket.document_key}`, ticket,
    ])).values()];
    const shownTickets = answer ? usedSources : (data.session_id ? [] : data.results);
    const usedFooter = usedTickets.length ? `<section class="knowledge-used-sources" aria-label="Tickets utilizados nesta resposta"><p>Tickets utilizados nesta resposta</p><div>${usedTickets.map(ticket =>
      `<button class="knowledge-source" type="button" data-document="${esc(ticket.document_key)}" title="${esc(ticket.title)}">${esc(ticket.ticket_reference ? `Ticket #${ticket.ticket_reference}` : ticket.title || ticket.source_id)}</button>`).join("")}</div></section>` : "";
    // Na conversa, a resposta é a própria mensagem do assistente, sem outro cartão.
    const generated = answer && !data.session_id ? assistantMessage(answerText(answer)) : "";
    const citations = answer ? `<section class="knowledge-evidence"><h3>Evidências da resposta</h3>${answer.paragraphs.map(p =>
      p.citations.map(c => `<blockquote>${esc(c.quote)}</blockquote><button class="ghost" type="button" data-document="${esc(c.document_key)}">Consultar fonte · ${esc(c.source_id)}</button>`).join("")).join("")}</section>` : "";
    const generate = !data.session_id && data.generation_available && data.results.length && !answer
      ? '<div class="knowledge-local-answer"><p>Você também pode pedir uma orientação baseada nesses casos. A pergunta e até cinco trechos serão enviados ao Google Gemini.</p><button class="ghost" type="button" data-generate>Gerar orientação</button></div>'
      : (!data.generation_available ? '<p class="knowledge-status">A pesquisa é local. A geração com Gemini ainda não está ativada no servidor.</p>' : "");
    const usage = data.usage?.input_tokens ? `<p class="knowledge-usage">Entrada: ${esc(data.usage.input_tokens)} / ${esc(data.usage.input_limit)} tokens${Number.isInteger(data.usage.totalTokenCount) ? ` · Total da geração: ${esc(data.usage.totalTokenCount)} tokens` : ""}.</p>` : "";
    const tickets = shownTickets.map(r => r.has_solution === false
        ? `<article class="knowledge-card"><h2>${esc(r.title)}</h2>
          <p>Atendimento relacionado · sem solução registrada no acervo.</p>
          <p><strong>${r.ticket_reference ? `Ticket ${esc(r.ticket_reference)}` : `Referência ${esc(r.source_id)}`}</strong></p>
          <p>Consulte o atendimento original no sistema de tickets para verificar as ações realizadas e o desfecho.</p></article>`
        : `<article class="knowledge-card"><h2>${esc(r.title)}</h2>${policy(r.metadata)}
        <pre>${esc(r.excerpt)}</pre><p class="knowledge-reference">Trecho ${r.position} · caracteres ${r.start + 1}–${r.end} do texto preparado</p>${reference(r)}
        <button class="ghost" type="button" data-document="${esc(r.document_key)}">Consultar conteúdo da fonte</button></article>`).join("");
    const details = shownTickets.length ? `<details class="knowledge-ticket-details"><summary><svg aria-hidden="true" viewBox="0 0 24 24"><path d="m9 5 7 7-7 7"/></svg><span>${answer ? "Detalhar tickets utilizados" : "Detalhar tickets encontrados"}</span><span class="knowledge-ticket-count">${answer ? usedTickets.length : shownTickets.length}</span></summary><div class="knowledge-ticket-content">${citations}${tickets}${usage}</div></details>`
      : (!data.session_id ? '<p class="knowledge-status">Nenhum ticket relacionado foi encontrado. Tente descrever o sintoma ou a mensagem de erro.</p>' : "");
    const diagnostics = !data.results.length && usage ? `<details class="knowledge-diagnostics"><summary>Informações da consulta</summary>${usage}</details>` : "";
    results.innerHTML = generated + usedFooter + notice + generate + details + diagnostics;
  }
  async function search(localOnly = false, retrying = false) {
    if (busy) return;
    if (!localOnly && conversationClosed) { error.textContent = "Inicie uma nova investigação para outro problema."; return; }
    const query = input.value.trim();
    if (!query) { input.focus(); error.textContent = "Informe o problema que deseja pesquisar."; return; }
    beforeSearch(query);
    chatView?.classList.add("has-conversation");
    controls(true); error.textContent = "";
    // A dúvida já foi enviada: libera a caixa para a próxima mensagem.
    if (!localOnly) { input.value = ""; input.dispatchEvent(new Event("input")); }
    lastRequest = null;
    const previousResults = results.innerHTML;
    const previousTranscript = transcript?.innerHTML || "";
    if (!localOnly && transcript) {
      transcript.innerHTML = previousTranscript + (retrying ? "" : userMessage(query))
        + assistantMessage('<p class="knowledge-thinking" role="status">Pensando<span aria-hidden="true">…</span></p>');
      results.innerHTML = "";
    } else {
      results.innerHTML = '<p class="knowledge-thinking" role="status">Pesquisando…</p>';
    }
    try {
      let data;
      if (localOnly) {
        data = await api("/knowledge/search", { method: "POST", body: { query } });
        conversationId = null; pendingRequest = null; conversationClosed = false;
        currentOptions = [];
        retryMessage = "";
        if (transcript) transcript.innerHTML = "";
        input.placeholder = initialPlaceholder;
        lastRequest = { query };
      } else {
        if (!pendingRequest || pendingRequest.message !== query) {
          pendingRequest = { message: query, request_id: crypto.randomUUID(), ...(conversationId ? { session_id: conversationId } : {}) };
        }
        data = await api("/knowledge/conversation", { method: "POST", body: pendingRequest });
        pendingRequest = null; conversationId = data.session_id;
        const retryable = ["rejected", "unavailable", "rate_limited", "busy"].includes(data.generation_status);
        retryMessage = retryable ? query : "";
        conversationClosed = !retryable && (data.turn >= 6 || data.decision === "answer");
        currentOptions = data.decision === "ask" && !conversationClosed ? (data.clarification_options || []) : [];
        const choices = currentOptions.length ? `<ol class="knowledge-options" aria-label="Escolha uma alternativa">${currentOptions.map((option, index) => `<li><button type="button" data-option="${index}"><span class="knowledge-option-number" aria-hidden="true">${index + 1}.</span><span>${esc(option.label)}</span></button></li>`).join("")}</ol><button class="knowledge-other" type="button" data-other>Nenhuma dessas — vou descrever</button>` : "";
        const response = data.generated_answer ? answerText(data.generated_answer)
          : `<p>${esc(technicalFailures[data.generation_status] || data.follow_up || (conversationClosed
              ? "Não encontrei evidências suficientes para orientar este caso. Você pode iniciar uma nova investigação com mais detalhes."
              : "Ainda não tenho informações suficientes para orientar. Pode descrever melhor o que acontece?"))}</p>`;
        if (transcript) transcript.innerHTML = data.messages.map(t =>
          (t.asked ? assistantMessage(`<p>${esc(t.asked)}</p>`) : "") + userMessage(t.message)).join("")
          + assistantMessage(response + choices + (retryable ? '<button class="ghost knowledge-retry" type="button" data-retry>Tentar novamente</button>' : ""));
        input.value = "";
        input.placeholder = data.follow_up ? "Responda à pergunta do assistente…" : initialPlaceholder;
        input.dispatchEvent(new Event("input"));
      }
      render(data);
      if (!localOnly) transcript?.lastElementChild?.scrollIntoView?.({ block: "start" });
    } catch (ex) {
      results.innerHTML = previousResults;
      if (transcript) transcript.innerHTML = previousTranscript;
      error.textContent = ex.message;
      if (!localOnly) { input.value = query; input.dispatchEvent(new Event("input")); }
    }
    finally { controls(false); if (!localOnly) input.focus({ preventScroll: true }); }
  }
  form.addEventListener("submit", e => { e.preventDefault(); search(); });
  if (local) local.onclick = () => search(true);
  if (transcript) transcript.addEventListener("click", e => {
    if (busy || conversationClosed) return;
    if (e.target.closest("[data-retry]")) {
      if (!retryMessage) return;
      input.value = retryMessage;
      search(false, true);
      return;
    }
    const option = e.target.closest("[data-option]");
    if (option) {
      const choice = currentOptions[Number(option.dataset.option)];
      if (!choice) return;
      input.value = choice.label;
      input.dispatchEvent(new Event("input"));
      search();
    } else if (e.target.closest("[data-other]")) {
      input.placeholder = "Descreva o que acontece no seu caso…";
      input.focus();
    }
  });
  results.addEventListener("click", async e => {
    const generate = e.target.closest("[data-generate]");
    if (generate) {
      if (busy || !lastRequest) return;
      controls(true); generate.disabled = true; error.textContent = "";
      generate.textContent = "Gerando resposta…";
      try {
        render(await api("/knowledge/answer", { method: "POST", body: lastRequest }));
      } catch (ex) {
        error.textContent = ex.message;
        generate.disabled = false; generate.textContent = "Tentar gerar novamente";
      } finally { controls(false); }
      return;
    }
    const button = e.target.closest("[data-document]");
    if (!button || button.disabled) return;
    button.disabled = true; error.textContent = "";
    try {
      const doc = await api(`/knowledge/documents/${encodeURIComponent(button.dataset.document)}`);
      $("#knowledge-document-title").textContent = doc.title;
      $("#knowledge-document-body").innerHTML = policy(doc.metadata) + reference(doc) + `<pre>${esc(doc.body)}</pre>`;
      $("#knowledge-document").showModal();
    } catch (ex) { error.textContent = ex.message; }
    finally { button.disabled = false; }
  });
}

if (document.body.dataset.page === "knowledge") initKnowledgeSearch();
