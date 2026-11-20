// T1 — Vazão de ingestão: >= 500 notificações/s com p95 da API < 200 ms.
//
// Três fases em sequência:
//   aquecimento   rampa de 50 até a meta (60 s)
//   patamar       taxa constante da meta (120 s)  <- a meta é avaliada só aqui
//   acima_da_meta rampa até TAXA_MAX (90 s)        <- procura o limite, sem meta
//
// Uso (ver tests/README.md):
//   k6 run --summary-export ../../docs/testes/dados/t1-ingestao.json ingestao.js
import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { cabecalhos, novaNotificacao, unidadeAleatoria, URL_NOTIFICACOES } from './lib/notificacao.js';

const TAXA_META = Number(__ENV.TAXA_META || 500);
const TAXA_MAX = Number(__ENV.TAXA_MAX || 700);
// Caminho absoluto, ou relativo a esta pasta (tests/load).
const TOKENS = __ENV.TOKENS_ARQUIVO ? JSON.parse(open(__ENV.TOKENS_ARQUIVO)) : null;

const aceitas = new Counter('notificacoes_aceitas');

export const options = {
  discardResponseBodies: true,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  scenarios: {
    aquecimento: {
      executor: 'ramping-arrival-rate',
      startRate: 50,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 600,
      stages: [{ target: TAXA_META, duration: '60s' }],
    },
    patamar: {
      executor: 'constant-arrival-rate',
      startTime: '60s',
      rate: TAXA_META,
      timeUnit: '1s',
      duration: '120s',
      preAllocatedVUs: 200,
      maxVUs: 800,
    },
    acima_da_meta: {
      executor: 'ramping-arrival-rate',
      startTime: '180s',
      startRate: TAXA_META,
      timeUnit: '1s',
      preAllocatedVUs: 200,
      maxVUs: 1000,
      stages: [
        { target: TAXA_MAX, duration: '60s' },
        { target: TAXA_MAX, duration: '30s' },
      ],
    },
  },
  thresholds: {
    'http_req_duration{scenario:patamar}': ['p(95)<200'],
    'checks{scenario:patamar}': ['rate>0.99'],
    // Métricas por fase, para o relatório:
    'http_req_duration{scenario:acima_da_meta}': [],
    'http_reqs{scenario:patamar}': [],
  },
};

export default function () {
  const unidade = unidadeAleatoria();
  const resposta = http.post(URL_NOTIFICACOES, JSON.stringify(novaNotificacao()), {
    headers: cabecalhos(unidade, TOKENS),
    tags: { name: 'POST /api/v1/notificacoes' },
  });
  const aceita = check(resposta, { 'status 202': (r) => r.status === 202 });
  if (aceita) {
    aceitas.add(1);
  }
}
