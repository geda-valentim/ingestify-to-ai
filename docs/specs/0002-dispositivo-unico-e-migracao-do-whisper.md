# 0002 — Dispositivo único (`DEVICE`) e a migração do Whisper para CPU→CUDA

| | |
|---|---|
| **Status** | Implementada |
| **Autor** | Geda Valentim |
| **Criada em** | 2026-08-26 |
| **Atualizada em** | 2026-08-26 |
| **Relacionadas** | — |
| **Substituída por** | — |

---

## 1. Problema

Antes de `shared/device.py` existir, "em qual dispositivo isto roda?" tinha três respostas
independentes e nenhuma delas era registrada em log:

| Componente | Como decidia | Resultado numa máquina com GPU |
|---|---|---|
| Docling | `device="auto"` interno do próprio Docling | `cuda:0`, em cada um dos ~10 processos worker, sem log |
| `openai-whisper` | sondava `torch.cuda.is_available()` sozinho | `cuda` |
| `faster-whisper` | default de config `whisper_device = "cpu"` | **`cpu`**, sempre |

Ou seja: numa caixa com GPU o Docling ia para a GPU e a transcrição ficava na CPU, por
omissão, sem que ninguém tivesse decidido isso. `DEVICE` unificou as três respostas num
lugar só (`backend/shared/device.py`), e `WHISPER_DEVICE` virou um override *por
componente* cujo default vazio significa "herde `DEVICE`".

O problema desta spec é o que essa unificação **quebra em silêncio**, e é medível:

- `git show 5fd6461^:.env.example` não contém nenhuma linha `DEVICE` nem `WHISPER_DEVICE`.
  A variável **não existia**. Logo **nenhum usuário atual a tem definida** — 100% da base
  instalada cai no caminho "herda `DEVICE`".
- `git show 5fd6461^:backend/shared/config.py:79` mostra `whisper_device: str = "cpu"`.
  O comportamento anterior de *todo mundo* era CPU.
- O único aviso de reconciliação que existia (`config.py::_warn_whisper_device_override`)
  só dispara quando o valor é **não-vazio** — isto é, exatamente no caso em que **nada
  mudou**. A população afetada não recebia sinal nenhum.

Somado ao defeito de empacotamento corrigido na mesma leva (o `requirements.txt` "ingênuo"
resolvia para o torch CUDA de PyPI e arrastava `nvidia-cudnn-cu13`), a cadeia completa era:

```
pip install -r backend/requirements.txt   → torch CUDA + nvidia-cudnn-cu13
DEVICE=auto                               → cuda (torch enxerga a GPU)
WHISPER_DEVICE vazio                      → herda cuda
faster-whisper → CTranslate2 → cuDNN cu12 → Unable to load libcudnn_ops.so.9
                                          → 500 em TODA transcrição
```

E a guarda que deveria impedir isso não impedia nada. `resolve_whisper_device()` decidia o
fallback com `ctranslate2.get_cuda_device_count() > 0`. Esse símbolo liga em
`ctranslate2::get_gpu_count` → `cuda::get_gpu_count()` → `cudaGetDeviceCount()`: ele conta
**GPUs visíveis** e não diz absolutamente nada sobre cuDNN. Em qualquer host com driver
NVIDIA ele devolve ≥ 1, o fallback nunca dispara, e o processo morre depois. O único caso
em que ele dispararia é um `ctranslate2` compilado sem CUDA — e aí `resolve_device()` já
teria devolvido `cpu` antes. Era código morto com um docstring que afirmava o contrário.

## 2. Objetivo

`DEVICE` é o único botão de dispositivo do stack; quem herda CUDA para áudio ou é capaz de
rodar CUDA de verdade, ou cai em CPU com um WARNING claro — e, de um jeito ou de outro,
quem tem o comportamento mudado por esta migração vê **uma** linha de log dizendo isso.

### Fora de escopo

- Mudar o default de `DEVICE` (continua `auto`).
- Fazer o Docling ou o Florence-2 terem guarda de capacidade própria. A falha do cuDNN é
  específica do CTranslate2; torch e transformers falham de formas que `resolve_device()`
  já cobre.
- Instalar/consertar wheels CUDA em runtime. A guarda diagnostica e degrada; quem quer GPU
  instala `requirements-cuda.txt` (ver `docs/GPU.md`).
- Reverter o default para `whisper_device="cpu"`. A incoerência CPU-Whisper ao lado de
  GPU-Docling era justamente o que se queria corrigir.

## 3. Critérios de aceitação

- [x] Dado `DEVICE=cuda` e `WHISPER_DEVICE` vazio, quando o CTranslate2 enxerga a GPU mas
      **não** oferece compute type CUDA (ou o `libcudnn_ops.so.9` não carrega), então o
      áudio resolve para `cpu` e um WARNING nomeia o motivo real.
- [x] Dado o mesmo cenário com o CTranslate2 plenamente funcional, então o áudio resolve
      para `cuda`.
- [x] Dado `WHISPER_DEVICE=cuda` explícito num host incapaz, então ainda assim resolve
      `cpu` com WARNING — nunca 500 por transcrição.
- [x] Dado `WHISPER_DEVICE` vazio e o áudio efetivamente indo para CUDA, então é emitido
      exatamente um WARNING dizendo que isso **mudou** e como voltar (`WHISPER_DEVICE=cpu`).
- [x] Dado `WHISPER_DEVICE=cpu`, então nenhum WARNING de migração é emitido (nada mudou
      para esse usuário) — só o WARNING de override que já existia em `config.py`.
- [x] Nenhum teste desta spec importa torch nem exige GPU real.

## 4. Solução proposta

### Fluxo

```
resolve_whisper_device()
  ├─ requested = WHISPER_DEVICE or DEVICE ; explicit = WHISPER_DEVICE não-vazio
  ├─ device = resolve_device(requested)          # 'auto' nunca falha; 'cuda' explícito falha
  ├─ device não começa com 'cuda'  ──▶ devolve device            (caminho da maioria)
  ├─ _ctranslate2_cuda_blocker()
  │     1. import ctranslate2                          .. falhou? motivo
  │     2. get_supported_compute_types('cuda')         .. levantou/vazio? motivo
  │     3. ctypes.CDLL('libcudnn_ops.so.9')            .. não carrega? motivo
  │     └─ motivo não-None ──▶ WARNING com o motivo ──▶ devolve 'cpu'
  └─ not explicit ──▶ WARNING de migração ──▶ devolve device
```

### Mudanças por camada

**Shared** (`backend/shared/device.py`)

- `_cudnn9_load_error() -> Optional[str]` — tenta `ctypes.CDLL` em
  `<site-packages>/nvidia/cudnn/lib/libcudnn_ops.so.9` (caminho absoluto **primeiro**, que
  é para onde o RPATH do wheel do ctranslate2 aponta e que normalmente **não** está no
  loader path do sistema) e depois no soname puro. Nunca levanta.
- `_ctranslate2_cuda_blocker() -> Optional[str]` — `None` quando o CTranslate2 realmente
  roda em CUDA aqui; caso contrário a string do *porquê*, que vai literal para o log.
- `resolve_whisper_device()` — usa o blocker no lugar de `get_cuda_device_count()`, aplica
  o fallback também para pedido explícito, e emite o WARNING de migração via `_log_once`.

**Config** (`backend/shared/config.py`) — inalterado. O WARNING de override
(`WHISPER_DEVICE=x overrides DEVICE=y`) continua no validator, porque ali ele tem os dois
valores e não custa nada. O WARNING complementar (herança) **não** pode viver ali: ele
depende do dispositivo resolvido, o que exige sondar torch, e config não sonda torch.

**Ops** (`.env.example`) — o bloco `WHISPER_DEVICE` aponta para esta spec e descreve os
dois WARNINGs (override e migração) em vez de só o primeiro.

## 5. Alternativas consideradas

| Alternativa | Por que foi descartada |
|---|---|
| Manter `ctranslate2.get_cuda_device_count() > 0` | Conta GPUs visíveis via `cudaGetDeviceCount()`; não diz nada sobre cuDNN. Em host com driver devolve ≥1 e a guarda nunca dispara. É o defeito, não a correção. |
| Só `get_supported_compute_types('cuda')`, sem o probe de cuDNN | Melhor que o anterior — inicializa o backend CUDA de verdade — mas enumera capacidade de *compute* do device. Não é garantido que toque no `libcudnn_ops`. Fica como etapa 2, não como resposta final. |
| Só checar se `nvidia.cudnn` é importável | Um `nvidia-cudnn-cu13` importa perfeitamente e é exatamente a árvore quebrada. Presença ≠ carregabilidade. |
| Exigir `WHISPER_DEVICE=cuda` explícito para áudio ir à GPU | Resolve a regressão de forma trivial, mas restaura a incoerência CPU-Whisper/GPU-Docling por omissão e transforma "herdar `DEVICE`" em mentira. O WARNING de migração dá o mesmo aviso sem custar a coerência. |
| Deixar estourar o `Unable to load libcudnn_ops.so.9` | É o status quo: 500 em toda transcrição, com uma mensagem que não diz o que fazer. |
| Levantar `DeviceUnavailableError` quando `WHISPER_DEVICE=cuda` explícito é incapaz | Consistente com `DEVICE=cuda`, mas transcrição é uma feature entre várias: derrubar o worker inteiro por causa dela é pior que degradar com log. |

## 6. Impactos

- **Compatibilidade:** o único comportamento que muda em relação a `5fd6461` é para quem
  tem CUDA de verdade funcionando e `WHISPER_DEVICE` vazio — e essa pessoa agora recebe um
  WARNING explícito. Quem não tem cuDNN utilizável deixa de receber 500 e volta ao
  comportamento pré-`5fd6461` (CPU). Para voltar ao antigo em qualquer caso:
  `WHISPER_DEVICE=cpu`.
- **Performance:** o blocker roda uma vez por processo (`_log_once` cobre só o log; o
  caminho não-CUDA sai antes de qualquer import). `ctypes.CDLL` de uma lib já mapeada é
  barato e só é alcançado em host CUDA.
- **Segurança:** nenhuma. Nenhuma entrada de usuário chega aqui; os nomes de biblioteca
  são constantes do código.
- **Operação:** nenhuma variável nova. Dois WARNINGs novos possíveis no boot do worker,
  ambos com ação concreta no texto.
- **Custo:** nenhum.

## 7. Plano de testes

- **Unitários** (`backend/tests/test_device.py`, `backend/tests/test_device_whisper_guard.py`):
  `ctranslate2` é um `types.ModuleType` falso injetado em `sys.modules`, e `nvidia.cudnn` /
  `ctypes.CDLL` são monkeypatchados. Cobrem: GPU visível + compute type ausente (o caso que
  a guarda antiga deixava passar), `get_supported_compute_types` levantando, cuDNN não
  carregável, caminho feliz, pedido explícito incapaz, e presença/ausência do WARNING de
  migração.
- **Integração:** nenhuma. Exercitar o caminho real exige GPU e não roda em CI.
- **Manual:** numa caixa com GPU, `make gpu` e conferir uma das três linhas no
  `docker compose logs worker`.

## 8. Plano de implementação

- [x] Trocar a guarda de `get_cuda_device_count()` pelo blocker de três etapas.
- [x] Aplicar o fallback também ao pedido explícito.
- [x] Emitir o WARNING de migração para quem herda CUDA.
- [x] Apontar `.env.example` para esta spec.
- [x] Testes com `ctranslate2` mockado.

## 9. Questões em aberto

- [ ] `_cudnn9_load_error()` procura em dois caminhos; o wheel do ctranslate2 poderia mudar
      o RPATH numa versão futura. → **Decisão (2026-08-26):** aceitável. Um falso negativo
      degrada para CPU com log — direção segura — e o log nomeia o caminho tentado.
- [ ] Vale estender a mesma guarda de capacidade a Florence-2? → **Decisão (2026-08-26):**
      não por ora. `transformers`/torch falham de formas que `resolve_device()` já cobre;
      só o CTranslate2 traz sua própria cuDNN.
