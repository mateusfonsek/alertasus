// Geração de notificações e autenticação para os scripts k6.
// Segue docs/contratos/evento-notificacao.md.
import { randomIntBetween, randomItem, uuidv4 } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

export const ALVO_URL = __ENV.ALVO_URL || 'http://localhost:8001';
export const URL_NOTIFICACOES = `${ALVO_URL}/api/v1/notificacoes`;
export const N_UNIDADES = Number(__ENV.UNIDADES || 50);

// Mesma lista da seção 4 do contrato.
const MUNICIPIOS = {
  '2507507': ['Mangabeira', 'Bancários', 'Manaíra', 'Cristo Redentor', 'Valentina', 'Torre', 'Centro', 'Cruz das Armas'],
  '2504009': ['Bodocongó', 'Catolé', 'Liberdade', 'Centro', 'Malvinas', 'José Pinheiro'],
  '2513703': ['Centro', 'Tibiri', 'Várzea Nova'],
  '2501807': ['Centro', 'Mário Andreazza', 'Alto da Boa Vista'],
  '2503209': ['Centro', 'Intermares', 'Camboinha'],
  '2510808': ['Centro', 'Jatobá', 'Belo Horizonte'],
  '2516201': ['Centro', 'Gato Preto', 'Estreito'],
  '2503704': ['Centro', 'Remédios', 'Cristo Rei'],
};
const CODIGOS = Object.keys(MUNICIPIOS);
const AGRAVOS = ['dengue', 'dengue', 'sindrome_gripal', 'sindrome_gripal', 'chikungunya'];

function hojeLocal() {
  const agora = new Date();
  return new Date(agora.getTime() - agora.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function unidadeAleatoria(primeira = 1) {
  return `unidade-${String(randomIntBetween(primeira, N_UNIDADES)).padStart(3, '0')}`;
}

export function novaNotificacao() {
  const municipio = randomItem(CODIGOS);
  const hoje = hojeLocal();
  return {
    notificacao_id: uuidv4(),
    agravo: randomItem(AGRAVOS),
    municipio_ibge: municipio,
    bairro: randomItem(MUNICIPIOS[municipio]),
    data_inicio_sintomas: hoje,
    data_notificacao: hoje,
    enviado_em: new Date().toISOString(),
  };
}

// Sem tokens: modo direto (cabeçalho que o Gateway injetaria).
// Com tokens: modo Gateway (JWT da unidade).
export function cabecalhos(unidade, tokens) {
  const base = { 'Content-Type': 'application/json' };
  if (!tokens) {
    return Object.assign(base, { 'X-Consumer-Username': unidade });
  }
  return Object.assign(base, { Authorization: `Bearer ${tokens[unidade]}` });
}
