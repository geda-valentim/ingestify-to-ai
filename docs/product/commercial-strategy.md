# Estratégia comercial do Ingestify

O Ingestify pode ser vendido como infraestrutura de processamento de documentos, imagens e conversas para empresas que desenvolvem aplicações de IA. O primeiro mercado proposto são integradores e agências com fluxos recorrentes de clientes. A hipótese comercial é economizar integração e operação, mantendo resultados organizados na infraestrutura escolhida pelo cliente.

Esta estratégia orienta pilotos e decisões de produto. As funcionalidades da tabela de prioridades são propostas, com critérios de validação; não fazem parte de uma oferta já disponível. Revisão: 7 de outubro de 2026. A análise de alternativas está em [Comparação com Unstructured](unstructured-comparison.md).

## Público e problema inicial

| Prioridade | Cliente e comprador | Usuário | Trabalho a resolver | Evidência que valida a oportunidade |
| --- | --- | --- | --- | --- |
| 1 | Agência ou consultoria de IA; fundador ou líder técnico | Desenvolvedor que integra sistemas de clientes | Receber arquivos, obter resultados e entregá-los no storage do cliente sem manter um pipeline diferente para cada projeto | Dois fluxos recorrentes do mesmo cliente, com uso real, implantação repetível e pagamento pelo processamento ou operação |
| 2 | Empresa com produto de agentes ou automação; CTO ou líder de engenharia | Desenvolvedor de backend ou plataforma | Incorporar ingestão de arquivos e conversas por API, com acompanhamento, retry e resultados recuperáveis | Integração em uma aplicação utilizada pelos clientes, com redução mensurável do trabalho de engenharia |
| 3 | Equipe interna de dados; líder de tecnologia ou dados | Engenheiro de dados e operador | Transformar conteúdo disperso em dados organizados para seus sistemas de análise | Um processo frequente substituído, com qualidade e custo aceitos pela equipe |
| Posterior | Atendimento, vendas ou sucesso do cliente; gestor da operação com patrocinador técnico | Supervisor ou analista | Consultar histórico e analisar conversas de cada cliente | Uma decisão operacional melhorada por uma análise consolidada; transcripts isolados não bastam |

O primeiro piloto deve escolher um desses públicos e um fluxo específico. Misturar processamento documental, análise de chamadas e avaliação visual em uma mesma venda dificultaria descobrir pelo que o cliente paga. Um integrador com necessidade recorrente de ingestão é o melhor ponto de partida proposto; a prioridade muda se as entrevistas revelarem demanda paga mais forte por outro fluxo.

## O que a oferta atual suporta

O núcleo combina conversão de documentos, análise de imagens, transcrição de arquivos pela API, projetos e pastas, busca textual e acompanhamento de jobs. Full Analysis e faces têm entrega a S3, MinIO, Google Cloud Storage e Azure Blob Storage, com particionamento e exportação JSONL por atributos como cliente e data. Neste commit, as rotas gerais de documentos e transcrição não vinculam um destino de datalake; a infraestrutura reutilizável não significa cobertura já conectada de todas as modalidades. Engines e perfis controlam execução e recursos locais ou remotos conforme o adapter e as features habilitadas.

A cobertura da interface é menor que a da API. `/convert` envia documentos e imagens; áudio e vídeo gravados usam `/transcribe` pela API. `/live` captura microfone quando o serviço está habilitado. As abas URL, Google Drive e Dropbox de `/convert` ainda exibem “coming soon”. A seleção de datalake no envio está nas opções Full Analysis e faces. Para documentos e transcrições, entregar ao storage do cliente exige integração externa após obter o resultado, ou implementar o vínculo do destino nessas rotas. Há adapters capazes de ler objetos de storage, mas não foi encontrada rota pública conectada para ingestão de objetos; não anunciar sincronização de bucket como pronta. Os novos [guias de plataforma](../../frontend/app/docs/platform-guides.tsx) devem explicar essas diferenças ao usuário.

Projetos e pastas organizam dados de um dono. O controle granular existente em engines e perfis não equivale a organizações comerciais com membros, convites e papéis sobre todos os dados. O ledger de engines mede e reconcilia custos de infraestrutura; não constitui faturamento SaaS, assinatura ou cobrança ao cliente. A busca existente é textual: um pipeline completo de recuperação com chunks, embeddings e índice vetorial ainda exige trabalho adicional.

A promessa pública deve permanecer verificável: **processar conteúdo e entregar dados organizados para a aplicação do cliente**. Resultados estruturados de uma imagem não garantem uma decisão de negócio correta. Particionar conversas por `customer_id` não executa automaticamente análise do histórico daquele cliente.

## Oferta de piloto

Proposta inicial: implantação assistida de um fluxo com uma modalidade principal, um destino e critérios de qualidade acordados. O cliente fornece amostras representativas e a aplicação que consumirá os resultados. O piloto inclui integração, processamento acompanhado, entrega e diagnóstico; a análise de negócio só entra no escopo se for explicitamente desenvolvida.

Há duas formas de entrega a validar. Uma instalação dedicada atende quem já possui infraestrutura e prefere operação isolada. Uma oferta hospedada simplifica a adoção, mas depende de controles comerciais e operacionais adicionais antes de receber vários clientes. Não anunciar disponibilidade geral, SLA ou certificações sem a respectiva implantação e evidência.

O contrato experimental pode separar implantação de operação recorrente. Valores de venda serão definidos após medir o custo real e entrevistar compradores; esta estratégia não fixa preços nem prevê receita. Pilotos pagos manualmente podem anteceder checkout e assinatura automatizados.

## Funcionalidades propostas

As prioridades abaixo são uma decisão inicial para validação. Esforço é relativo: pequeno envolve um fluxo existente; médio conecta componentes e persistência; grande muda autorização, arquitetura ou operação. Esses rótulos não são estimativas de prazo.

| Prioridade | Funcionalidade | Benefício comercial | Escopo e dependências | Esforço | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| P0 | Fluxo de onboarding com exemplo completo | Reduz assistência necessária para começar | Primeiro resultado, projeto, destino e guia contextual; reaproveitar o que já está disponível | Pequeno a médio | Um novo usuário conclui o fluxo escolhido e encontra o resultado sem intervenção do desenvolvedor |
| P0 | Painel de confiabilidade e custo por processamento | Permite operar um piloto e calcular margem | Erro acionável, resultado recuperável, tempos de fila e execução, custo com origem e confiabilidade da estimativa; distinguir falha de processamento de falha de entrega | Médio | Reconciliação de amostras com logs e ledger; retries e custo desconhecido não desaparecem da conta |
| P0 para SaaS compartilhado | Organizações e acesso aos dados | Viabiliza vender a equipes e integradores com vários clientes | Organizações, membros, convites e escopos para projeto/job/storage; avaliar evolução IAM em branch própria antes de duplicar trabalho | Grande | Testes impedem leitura, busca, exportação, operação e acesso a credenciais entre clientes, inclusive por API key |
| P1 | Entrega de documentos e transcrições a datalakes | Completa a receita de ingestão por cliente | Conectar destino, snapshot e export existentes às rotas gerais; definir formatos, falhas, exclusão e retries; preservar autorização e contexto | Médio | Um documento e um áudio reais chegam ao destino por interface/API conforme o contrato; falha de entrega não apaga resultado e retry não cria conflito |
| P1 | Webhooks de conclusão, falha e entrega | Facilita integração sem polling permanente | Eventos duráveis, assinatura, tentativas, replay e documentação de duplicação; consumidores idempotentes | Médio | Uma aplicação recebe eventos verificáveis, tolera duplicados e recupera notificações após indisponibilidade |
| P1 | Ingestão em lote e recorrente de um bucket | Atende fluxos frequentes que justificam recorrência | Seleção de objetos, limites, checkpoint, identidade/versionamento, deduplicação e progresso por arquivo | Médio a grande | Interrupção e retomada não repetem arquivos concluídos; alteração no objeto gera processamento controlado |
| P1 | Templates por resultado desejado | Simplifica escolha e controla custo | Configuração reutilizável do job, distinta de perfis de infraestrutura; exemplos extração documental, OCR e conversa | Médio | Interface e API resolvem o mesmo template versionado, exibem o escopo e preservam a configuração na execução |
| P1 se escolhido o público de conversas | Histórico e análise por cliente | Entrega uma utilidade além do transcript | Identificadores cliente/conversa/canal, associação de jobs, autorização e janela temporal; análise com referências aos trechos originais | Grande | Consultar todas as conversas autorizadas de um cliente e gerar análise reproduzível com cobertura, período e fontes explícitos |
| P2 | Medição e faturamento por cliente | Automatiza a operação comercial após provar demanda | Medidor versionado, quotas, limites, plano, excedente e conciliação; ledger de infraestrutura é uma entrada, não a fatura | Grande | Um cliente consegue entender a cobrança; reprocessamentos e retries seguem regras explícitas e auditáveis |
| P2 conforme demanda | Chunking e entrega a índice vetorial | Reduz trabalho em aplicações de recuperação de conhecimento | Elementos com referências de origem, estratégia de chunks, embeddings versionados, atualização e exclusão | Grande | Recuperação e respostas avaliadas em corpus real; mudanças e exclusões mantêm o índice coerente |
| P2 conforme demanda | Extração documental com schema | Produz dados utilizáveis em uma automação específica | Schema do cliente, tipos validados, proveniência, campos ausentes e correção humana; começar por um tipo documental | Médio a grande | Precisão por campo e revisão humana avaliadas em corpus separado; custo por documento aceito justifica substituir o fluxo atual |
| P2 conforme demanda | Conectores e sincronização com sistemas do cliente | Aumenta recorrência e cobertura de fontes | Escolher um conector solicitado em pilotos; autenticação, cursor, alterações, exclusões, limites e manutenção | Médio a grande por conector | Sincronização incremental e revogação de acesso verificadas; nenhuma necessidade de copiar arquivos manualmente |

Webhooks de jobs são uma proposta distinta do webhook de alertas de engines existente. Há também um helper legado `send_callback` no worker e um campo `callback_url` em schema; as rotas gerais inspecionadas não encaminham esse parâmetro. Não tratá-los como contrato público de entrega assinada, durável e uniforme entre modalidades. Templates de processamento também diferem dos perfis de runtime: o primeiro descreve o que produzir; o segundo define onde e com quais recursos executar. O domínio de organizações deve ser coordenado com a implementação IAM em andamento, sem vender uma branch ainda não integrada como recurso disponível.

Não priorizar um catálogo maior de modelos ou executar todas as análises por padrão antes de provar utilidade. Full Analysis permanece útil para exploração; a operação recorrente pode precisar de um template menor, validado para aquele resultado e custo. Tampouco prometer equivalência de qualidade ou menor preço que a Unstructured sem benchmark comparável.

## Histórico de conversas como caso comercial

O exemplo de agente atendendo um cliente é uma hipótese de produto relevante. A ingestão aceitaria `customer_id`, `conversation_id`, `channel` e `occurred_at` como metadados validados. O particionamento continuaria cuidando do destino dos arquivos, enquanto um índice autorizado permitiria consultar conversas e evidências sem depender de listar diretórios do bucket.

Esses campos são uma proposta de contrato futuro. No contrato atual de datalake, chaves customizadas são strings em `partition_values`, e exemplos usam `client_id`, `conversation_id` e `agent_id`. Valores fora da estratégia preservam contexto sem criar diretórios. Não há campos de cliente/canal/hora de ocorrência nativos com índice e semântica temporal de conversas; o particionamento por data usa a criação do job. Essa distinção evita tratar o horário do processamento como o horário da conversa.

Uma análise consolidada precisaria explicitar cliente, período, conversas incluídas e modelo/template utilizado. Cada conclusão teria referências ao job, segmento ou timestamp que a sustenta. Reexecutar a análise após novas conversas criaria uma versão, preservando a anterior e respeitando exclusões e permissões. Resumo de histórico, pendências e temas recorrentes são primeiros resultados a testar; previsão de intenção ou interpretação emocional exige avaliação específica e não deve ser uma promessa automática.

A primeira validação pode usar um conjunto pequeno de conversas com critérios manuais. Só construir dashboards amplos ou integração CRM após o comprador demonstrar que usa a análise para agir. Essa etapa representa funcionalidade nova, não uma consequência já pronta do particionamento JSONL.

## Medição de qualidade e margem

Avaliar a modalidade do piloto com um corpus consentido e representativo: documentos escaneados e digitais, fotos difíceis ou áudio com ruído e falantes, conforme o caso. Registrar qualidade por classe de entrada, latência mediana e de cauda, falhas, truncamentos, intervenção manual e taxa de entrega. A classificação de expressão facial não equivale a diagnóstico ou conhecimento do estado interno de alguém.

Calcular margem de contribuição do fluxo: receita do período menos custos variáveis de processamento, armazenamento, transferência, serviços contratados e suporte atribuível. Reservas ou custos estimados precisam de identificação; recursos ociosos e a manutenção da implantação não podem ser ignorados no resultado econômico. Minutos de áudio, páginas e imagens têm custos diferentes: manter essas unidades separadas até existir uma regra comercial compreensível.

## Validação comercial

1. Entrevistar compradores de um único segmento sobre o fluxo atual, frequência, volume, erros, integração e quem aprova o orçamento. Mostrar uma demonstração orientada ao resultado, e perguntar qual trabalho ela substituiria.
2. Conseguir três pilotos pagos com o mesmo problema principal. Formalizar escopo, dados, destino, sucesso e responsabilidade operacional. Três pilotos são uma meta proposta, não tração já obtida.
3. Medir tempo até o primeiro resultado, uso recorrente, falhas, qualidade aceita, custo e minutos de suporte. Comparar o fluxo com a solução atual de cada cliente, incluindo código próprio quando essa for a alternativa.
4. Ao fim do piloto, verificar renovação, recomendação e expansão de volume. Uso recorrente com margem e pouco trabalho especial sustenta produto; receita baseada em customização constante aponta para serviço de integração.
5. Priorizar a próxima funcionalidade a partir de um bloqueio repetido em clientes pagantes. Reavaliar o público se ninguém aceitar pagar ou renovar, mesmo que a demonstração receba elogios.

## Limites de comunicação comercial

A página [Ingestify for Business](../../frontend/app/business/page.tsx) apresenta capacidades existentes e direciona para fluxos de uso e integração. Manter preços, certificações, depoimentos, SLA, colaboração entre equipes e futuras análises consolidadas fora das afirmações de disponibilidade até serem comprovados. Informar pré-requisitos de infraestrutura e features opcionais nos guias ligados à página.

## Evidências do produto

- [Rotas de documentos e transcrição](../../backend/api/routes.py) e [API frontend](../../frontend/lib/api.ts): processamento e recuperação dos resultados; conferir os endpoints e formatos antes de montar uma oferta.
- [Modelos persistidos](../../backend/shared/models.py) e [autorização por dono](../../backend/api/deps.py): escopo atual dos recursos e histórico de execução.
- [Particionamento de datalake](../../backend/shared/datalake/partitioning.py): estratégia, valores customizados e caminhos; conferir a implementação vigente para desenhar o caso de cliente.
- [Envio pela interface](../../frontend/app/convert/page.tsx), [seletor de arquivo](../../frontend/components/upload/file-upload.tsx) e [captura ao vivo](../../frontend/app/live/page.tsx): limites de cobertura da interface.
- [Controle e acesso de engines](../../backend/shared/access) e [ledger](../../backend/shared/engines): operação e contabilidade de infraestrutura, sem faturamento comercial automático.
