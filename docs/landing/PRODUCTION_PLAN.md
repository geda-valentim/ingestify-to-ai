# Plano de produção do filme da home

O filme conecta os 16 quadros brancos com vidro líquido por 15 trechos contínuos: oito transformações e sete pontes. Cada trecho usa o mesmo arquivo exato no encontro com o seguinte. A geração será pela API Higgsfield, modelo `kling-video/o3/first-last-frame`, modo pro, três segundos por trecho, 16:9 e sem áudio.

## Sequência e custo

O total da mídia é 45 segundos. A rolagem define o tempo visto e permite períodos maiores de leitura nos resultados. A estimativa autenticada é US$ 0,286 por trecho, US$ 4,29 para 15 gerações, consultada em 5 de outubro de 2026. O limite de cotação é US$ 0,30 por trecho, preservando o guard do exemplo anexado, e US$ 4,50 para o conjunto. Isso é uma guarda de envio, não um teto imposto pelo provedor. Tentativas adicionais exigem revisão do orçamento.

| Ordem | Trecho | Primeiro quadro | Último quadro |
|---|---|---|---|
| 1 | scene-01 | scene-01-start.png | scene-01-end.png |
| 2 | bridge-01-02 | scene-01-end.png | scene-02-start.png |
| 3 | scene-02 | scene-02-start.png | scene-02-end.png |
| 4 | bridge-02-03 | scene-02-end.png | scene-03-start.png |
| 5 | scene-03 | scene-03-start.png | scene-03-end.png |
| 6 | bridge-03-04 | scene-03-end.png | scene-04-start.png |
| 7 | scene-04 | scene-04-start.png | scene-04-end.png |
| 8 | bridge-04-05 | scene-04-end.png | scene-05-start.png |
| 9 | scene-05 | scene-05-start.png | scene-05-end-v2.png |
| 10 | bridge-05-06 | scene-05-end-v2.png | scene-06-start.png |
| 11 | scene-06 | scene-06-start.png | scene-06-end.png |
| 12 | bridge-06-07 | scene-06-end.png | scene-07-start.png |
| 13 | scene-07 | scene-07-start.png | scene-07-end.png |
| 14 | bridge-07-08 | scene-07-end.png | scene-08-start.png |
| 15 | scene-08 | scene-08-start.png | scene-08-end.png |

O [manifesto completo](film-manifest.json) contém os prompts, as zonas de texto e as condições de cada trecho. A [galeria](README.md) mostra os arquivos exatos. As [observações da revisão independente](STORYBOARD_REVIEW.md) orientam as pontes.

## Interação com texto da página

A coluna de texto usa no máximo 26% da largura no desktop; nas pontes, só título curto com até 24%. O palco ocupa a largura completa e não recebe um véu que esconda os objetos. A largura real de texto e o enquadramento serão ajustados na prévia.

Cada resultado recebe HTML legível: pequeno Markdown no capítulo de documentos, segmentos com timestamps em áudio e exemplo OCR. O código da API fica abaixo do palco em seção dedicada. Nenhum desses conteúdos depende de letras geradas no vídeo. Apenas o capítulo ativo recebe interação; o conteúdo completo fica acessível em seções semânticas e na experiência estática.

“Visão de evolução” aparece antes da ponte 6→7 e permanece durante a ponte 7→8. Os componentes pontilhados são planos futuros. Áudio segue uma única rota na cena 5; documentos e imagens ficam locais. O vídeo refere-se à faixa de áudio.

A navegação por capítulos move a página à posição correspondente. O mesmo mapa controla o instante do filme e o texto nos dois sentidos. Parar a rolagem estabiliza o quadro. A última cena libera espaço antes de expandir a chamada final.

## Composição vertical e alternativa estática

No celular, o filme horizontal inteiro ocupa uma faixa visual 16:9, com texto e ações abaixo, dentro da composição vertical. Não haverá recorte central. A prévia a 390px deve comprovar que ambos os lados das transformações continuam reconhecíveis; exemplos legíveis ficam em HTML. Caso a faixa visual não comunique a transformação, a cena precisa de recomposição antes da publicação.

Com preferência por movimento reduzido ou economia de dados, os capítulos viram seções estáticas com os mesmos exemplos e destinos. Falha de vídeo exibe o quadro estático do capítulo e mantém todo o conteúdo navegável. Não carregar toda a sequência em PNG na abertura.

## Gates de revisão

1. Revisão independente do manifesto, incluindo as sete pontes e zonas HTML.
2. Storyboard aprovado na revisão independente; produção autorizada pela meta do usuário dentro dos limites de cotação antes das gerações pagas.
3. Gerar e inspecionar a cena 1 como piloto; enviar os demais trechos após verificar a direção.
4. Inspecionar movimento e emendas dos 15 vídeos reais. Corrigir saltos, fusões ou informação de produto incorreta.
5. Revisar a home renderizada, acessibilidade, reversão, âncoras, mobile, falha de mídia e desempenho.
6. Merge na main e publicação no ambiente existente, seguidos de verificação pública.

O GitHub foi conferido nesta preparação: o repositório está público. A chamada será “Ver no GitHub”; o aviso antigo de repositório privado deve ser removido da home. Isso não substitui a preparação de licença e instruções de contribuição.

## Referências da API

- [Modelo Kling O3](https://open.higgsfield.ai/models/kling-video/o3/first-last-frame/api-reference).
- [Estimativa e cobrança](https://docs.higgsfield.ai/docs/concepts/billing-and-retention).
- [Ciclo de vida e identificador da requisição](https://docs.higgsfield.ai/docs/concepts/requests).
