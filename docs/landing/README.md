# Quadros do filme da home

Dezesseis quadros de início e fim das oito cenas, com fundo branco, elementos pretos, vidro líquido transparente e linhas rainbow. A direção visual segue o [roteiro da landing](../LANDING_PAGE_BRIEF.md).

As imagens são referências de composição para a produção do filme. Texto da home, marca, botões, código e rótulos de disponibilidade entram como HTML sobreposto. As linhas coloridas representam o percurso a animar; estes arquivos são imagens estáticas.

## Galeria por cena

| Cena | Início | Fim |
|---|---|---|
| 1 Entrada dos arquivos | ![Início da cena 1](../../frontend/public/landing/storyboard/white-rainbow/scene-01-start.png) | ![Fim da cena 1](../../frontend/public/landing/storyboard/white-rainbow/scene-01-end.png) |
| 2 Documento em Markdown | ![Início da cena 2](../../frontend/public/landing/storyboard/white-rainbow/scene-02-start.png) | ![Fim da cena 2](../../frontend/public/landing/storyboard/white-rainbow/scene-02-end.png) |
| 3 Áudio em transcrição | ![Início da cena 3](../../frontend/public/landing/storyboard/white-rainbow/scene-03-start.png) | ![Fim da cena 3](../../frontend/public/landing/storyboard/white-rainbow/scene-03-end.png) |
| 4 Imagem em texto | ![Início da cena 4](../../frontend/public/landing/storyboard/white-rainbow/scene-04-start.png) | ![Fim da cena 4](../../frontend/public/landing/storyboard/white-rainbow/scene-04-end.png) |
| 5 Execução local e Modal | ![Início da cena 5](../../frontend/public/landing/storyboard/white-rainbow/scene-05-start.png) | ![Fim da cena 5](../../frontend/public/landing/storyboard/white-rainbow/scene-05-end-v2.png) |
| 6 Organização e API | ![Início da cena 6](../../frontend/public/landing/storyboard/white-rainbow/scene-06-start.png) | ![Fim da cena 6](../../frontend/public/landing/storyboard/white-rainbow/scene-06-end.png) |
| 7 Evolução distribuída | ![Início da cena 7](../../frontend/public/landing/storyboard/white-rainbow/scene-07-start.png) | ![Fim da cena 7](../../frontend/public/landing/storyboard/white-rainbow/scene-07-end.png) |
| 8 Encerramento | ![Início da cena 8](../../frontend/public/landing/storyboard/white-rainbow/scene-08-start.png) | ![Fim da cena 8](../../frontend/public/landing/storyboard/white-rainbow/scene-08-end.png) |

## Arquivos e produção

- Cópia solicitada: `/data/tmp/ingestify/white-rainbow/`.
- Arquivos versionados: `frontend/public/landing/storyboard/white-rainbow/`.
- Caminhos no frontend: `/landing/storyboard/white-rainbow/scene-01-start.png` e demais caminhos do manifesto.
- Geração e edição: ferramenta integrada `image_gen.imagegen`, pela skill `imagegen`.
- [Prompts completos e referências](image-prompts.json).
- O quadro final da cena 5 usa `scene-05-end-v2.png`, com o caminho de áudio exclusivamente ligado ao destino remoto.

Preserve a leitura de origem e resultado ao animar. A ligação entre cenas exige os movimentos de câmera e as transições descritos no roteiro; não faça apenas cortes secos entre estes quadros. A cena 7 precisa do rótulo HTML “Visão de evolução”, e o encerramento precisa do estado “Ver no GitHub”.

A versão horizontal desta galeria não substitui a futura composição vertical nem constitui um vídeo pronto. Os estudos escuros anteriores e a primeira versão do fim da cena 5 continuam na pasta local de trabalho, fora da seleção versionada.
