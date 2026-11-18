// Testa o controlador da tela sem navegador, Firebase ou chamadas ao Google.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');

function element() {
  return { value: '', innerHTML: '', textContent: '', placeholder: 'Descreva o problema',
    disabled: false, listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; },
    dispatchEvent() {}, focus() {}, close() {}, showModal() { this.open = true; } };
}
const elements = new Map();
const $ = selector => {
  if (!elements.has(selector)) elements.set(selector, element());
  return elements.get(selector);
};
const calls = [];
let handler;
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const context = vm.createContext({ $, esc, crypto: webcrypto, Event: class {},
  session: { token: 'fixture-only' }, document: { body: { dataset: { page: 'knowledge' } } },
  location: { replace() { throw Error('unexpected redirect'); } }, logout() {},
  api: async (path, options = {}) => { calls.push({ path, body: structuredClone(options.body) }); return handler(path, options.body); }
});
vm.runInContext(fs.readFileSync('acervo.js', 'utf8'), context);
const tick = () => new Promise(resolve => setImmediate(resolve));
async function send(text) {
  $('#knowledge-query').value = text;
  $('#knowledge-form').listeners.submit({ preventDefault() {} });
  await tick();
}
const ticket = {document_key:'a',source_id:'caso',title:'Ticket de teste <PLC>',excerpt:'Trecho técnico',
  metadata:{},origin:{registro_id:'caso',arquivo_relativo:'casos.jsonl'},position:1,start:0,end:14,has_solution:true,ticket_reference:'11813'};
const secondTicket = {...ticket,document_key:'b',source_id:'segundo',ticket_reference:'12000',title:'Segundo ticket citado'};
const discardedTicket = {...ticket,document_key:'c',source_id:'descartado',ticket_reference:'99999',title:'Ticket descartado da resposta'};
const duplicateTicket = {...ticket,document_key:'a2',source_id:'outro-caso-mesmo-ticket'};
const base = { results: [ticket,secondTicket,discardedTicket,duplicateTicket], warnings: [], generation_available: true, generated_answer: null };
(async () => {
  handler = () => ({ ...base, session_id: 'fixture-session', turn: 1, decision: 'ask',
    follow_up: 'Parou após uma alteração?', messages: [{message:'Falha <PLC>',asked:''}],
    clarification_options: [{label:'Após atualizar',quote:'Fonte fictícia'},{label:'Nunca funcionou <PLC>',quote:'Outra fonte fictícia'}],
    usage: {input_tokens:500,input_limit:4000} });
  await send('Falha <PLC>');
  assert.equal(calls[0].path, '/knowledge/conversation');
  assert.match($('#knowledge-conversation').innerHTML, /Falha &lt;PLC&gt;/);
  assert.match($('#knowledge-conversation').innerHTML, /Parou após/);
  assert.equal($('#knowledge-query').value, '');
  assert.equal($('#knowledge-submit').disabled, false);
  assert.match($('#knowledge-conversation').innerHTML, /data-option="0"/);
  assert.match($('#knowledge-conversation').innerHTML, /<ol class="knowledge-options"/);
  assert.doesNotMatch($('#knowledge-conversation').innerHTML, /<strong>Assistente/);
  assert.match($('#knowledge-conversation').innerHTML, /Nunca funcionou &lt;PLC&gt;/);
  assert.doesNotMatch($('#knowledge-results').innerHTML, /Detalhar tickets|Ticket de teste|Tickets utilizados/, 'esclarecimento não lista candidatos');
  const beforeOther = calls.length;
  $('#knowledge-conversation').listeners.click({target:{closest(selector) { return selector === '[data-other]' ? {} : null; }}});
  assert.equal(calls.length, beforeOther, 'escrever outra resposta não envia nada automaticamente');
  assert.match($('#knowledge-query').placeholder, /Descreva/);

  handler = () => ({ ...base, session_id: 'fixture-session', turn: 2, decision: 'answer',
    messages: [{message:'Falha <PLC>',asked:''},{message:'Após atualizar',asked:'Parou após uma alteração?'}],
    generated_answer: {paragraphs:[{text:'Confira a versão <driver>',citations:[
      {label:'F1',quote:'Versão incompatível',document_key:'a',source_id:'caso'},
      {label:'F2',quote:'Ação no segundo caso',document_key:'b',source_id:'segundo'}]},
      {text:'Confira as condições antes de aplicar.',citations:[{label:'F3',quote:'Condições do mesmo ticket',document_key:'a2',source_id:'outro-caso-mesmo-ticket'}]}]} });
  $('#knowledge-conversation').listeners.click({target:{closest(selector) { return selector === '[data-option]' ? {dataset:{option:'0'}} : null; }}});
  await tick();
  assert.equal(calls[1].body.message, 'Após atualizar');
  assert.equal(calls[1].body.session_id, 'fixture-session');
  assert.notEqual(calls[0].body.request_id, calls[1].body.request_id);
  assert.match($('#knowledge-conversation').innerHTML, /Confira a versão &lt;driver&gt;/);
  assert.doesNotMatch($('#knowledge-results').innerHTML, /Confira a versão &lt;driver&gt;/, 'resposta não se repete fora da conversa');
  assert.doesNotMatch($('#knowledge-conversation').innerHTML, /Confira a orientação e as fontes abaixo/);
  assert.match($('#knowledge-results').innerHTML, /knowledge-ticket-content.*Evidências da resposta/s);
  assert.doesNotMatch($('#knowledge-results').innerHTML, /<details[^>]*\bopen\b/);
  const footer = $('#knowledge-results').innerHTML.match(/<section class="knowledge-used-sources".*?<\/section>/s)[0];
  assert.match(footer, /Ticket #11813/);
  assert.match(footer, /Ticket #12000/);
  assert.equal((footer.match(/Ticket #11813/g) || []).length, 1, 'mesmo ticket citado mais de uma vez aparece uma vez');
  assert.doesNotMatch($('#knowledge-results').innerHTML, /99999|Ticket descartado/, 'candidato não citado não aparece nem nos detalhes');
  assert.match($('#knowledge-results').innerHTML, /Detalhar tickets utilizados/);
  assert.match($('#knowledge-results').innerHTML, /knowledge-ticket-count">2</);
  const count = calls.length;
  await send('Outro problema');
  assert.equal(calls.length, count, 'resposta final exige nova investigação');
  handler = () => ({title:'Fonte completa',body:'Conteúdo <seguro>',metadata:{},origin:{},source_id:'caso'});
  const documentButton = {dataset:{document:'a'}};
  await $('#knowledge-results').listeners.click({target:{closest(selector) { return selector === '[data-document]' ? documentButton : null; }}});
  assert.equal(calls.at(-1).path, '/knowledge/documents/a');
  assert.equal($('#knowledge-document').open, true);
  assert.match($('#knowledge-document-body').innerHTML, /Conteúdo &lt;seguro&gt;/);

  $('#knowledge-reset').onclick();
  assert.equal($('#knowledge-conversation').innerHTML, '');
  handler = () => { throw Error('Falha de rede simulada'); };
  await send('Novo problema');
  const failedId = calls.at(-1).body.request_id;
  assert.equal($('#knowledge-query').value, 'Novo problema');
  assert.equal($('#knowledge-submit').disabled, false);
  handler = () => ({ ...base, session_id:'next-session',turn:1,decision:'ask',follow_up:'Qual o erro?',messages:[] });
  await send('Novo problema');
  assert.equal(calls.at(-1).body.request_id, failedId, 'tentativa de rede preserva idempotência');
  assert.equal(calls.at(-1).body.session_id, undefined);

  handler = () => ({ ...base, generation_available:false });
  $('#knowledge-query').value = 'Consulta local';
  await $('#knowledge-local').onclick();
  assert.equal(calls.at(-1).path, '/knowledge/search');
  assert.equal($('#knowledge-conversation').innerHTML, '');
  assert.match($('#knowledge-results').innerHTML, /Detalhar tickets encontrados/);
  assert.match($('#knowledge-results').innerHTML, /Ticket descartado/, 'busca manual continua mostrando os candidatos');
  handler = () => ({ ...base, session_id:'fresh',turn:1,decision:'insufficient',messages:[] });
  await send('Nova pergunta');
  assert.equal(calls.at(-1).body.session_id, undefined, 'busca local encerra conversa anterior');
  $('#knowledge-reset').onclick();
  handler = () => ({...base,session_id:'retry-session',turn:1,decision:'insufficient',generation_status:'rejected',
    warnings:['A resposta não passou pela verificação de formato e referências.'],messages:[{message:'Erro ao clicar na Unit',asked:''}]});
  await send('Erro ao clicar na Unit');
  assert.match($('#knowledge-conversation').innerHTML, /não consegui validar/);
  assert.doesNotMatch($('#knowledge-conversation').innerHTML, /descrever melhor|informações suficientes/);
  assert.match($('#knowledge-conversation').innerHTML, /data-retry/);
  const rejectedRequest = calls.at(-1).body.request_id;
  handler = () => ({...base,session_id:'retry-session',turn:1,decision:'answer',generation_status:'generated',
    messages:[{message:'Erro ao clicar na Unit',asked:''}],generated_answer:{paragraphs:[{text:'Ação histórica registrada.',citations:[{label:'F1',quote:'Trecho original',document_key:'a',source_id:'caso'}]}]}});
  $('#knowledge-conversation').listeners.click({target:{closest(selector){return selector==='[data-retry]' ? {} : null;}}});
  await tick();
  assert.equal(calls.at(-1).body.message,'Erro ao clicar na Unit');
  assert.equal(calls.at(-1).body.session_id,'retry-session');
  assert.notEqual(calls.at(-1).body.request_id,rejectedRequest);
  assert.match($('#knowledge-conversation').innerHTML,/Ação histórica registrada/);
  console.log('OK: resposta com múltiplos tickets citados, deduplicação, descarte de candidatos, detalhes e conversa.');
})().catch(error => { console.error(error); process.exitCode = 1; });
