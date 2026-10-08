export const IMAGE_COPY = {
  pt: {
    imagesIntro:
      "Florence-2 oferece 15 tarefas de descrição, OCR, detecção, localização e segmentação. Use /images/analyze (JSON) ou /images/analyze/upload (multipart): wait=false retorna 202 com job_id; wait=true espera pelo resultado. As rotas específicas de descrição/OCR mantêm a espera síncrona. O front /convert oferece todas as tarefas e opções do catálogo.",
    imagesHead: ["Endpoint", "Entrada / saída"],
    imagesRows: [
      [
        "POST /images/analyze",
        "JSON: mode=single/full, image_base64, filename, opções e localização. 202 por padrão; wait=true espera.",
      ],
      [
        "POST /images/analyze/upload",
        "multipart: file, mode=single/full, opções JSON e localização. 202 por padrão; wait=true espera.",
      ],
      [
        "POST /images/{job_id}/cancel",
        "Somente Full Analysis: 202 enquanto executa; 200 terminal. Preserva resultados concluídos.",
      ],
      [
        "POST /images/describe/upload",
        "multipart: file, task opcional, tags, project/project_id e folder/folder_id. Retorna description e task.",
      ],
      [
        "POST /images/describe",
        "JSON: image_base64, filename opcional, task, tags como lista e localização. Mesma resposta de descrição.",
      ],
      [
        "POST /images/ocr/upload",
        "multipart: file, tags e localização. Retorna text e lines[].",
      ],
      [
        "POST /images/ocr",
        "JSON: image_base64, filename opcional, tags como lista e localização. Mesmo OCR; não recebe task.",
      ],
      [
        "GET /images/capabilities",
        "Estado do worker: dependencies_installed, model_downloaded, model_loaded, device_resolved, reason; tasks[], generation_schema/defaults, analysis_modes, full_profile e full_limits. Exige autenticação; não inicia inferência.",
      ],
    ],
    imageOptions:
      "PNG, JPEG, WEBP, BMP, GIF e TIFF, detectados pelos bytes. Limite padrão: 10 MB de imagem decodificada e 50 milhões de pixels (VISION_MAX_IMAGE_SIZE_MB / VISION_MAX_IMAGE_PIXELS). Base64 aceita prefixo data:image/...;base64, e quebras de linha. O projeto é obrigatório salvo vínculo da API key. JSON usa tags como lista; multipart aceita tags separadas por vírgula. Em single, repetir a imagem cria outro job; Full Analysis aplica Idempotency-Key. purge_source (padrão false) existe nas 8 rotas de envio (describe, ocr e analyze, JSON e /upload; faces e faces/upload): true apaga todas as cópias guardadas da imagem original quando o job termina (completed, ou failed/partial/cancelled; as rotas de imagem não têm retry automático) — a cópia local, o original e a prévia normalizada da análise completa/facial no armazenamento, e image.image_base64 do resultado guardado passa a null. O resultado da inferência (descrição, OCR, regiões, rostos, markdown) fica. Com wait=true, describe/ocr e analyze single ainda ecoam image_base64 no topo da resposta (vêm dos bytes desta requisição, não de uma cópia guardada); Full e faces devolvem image.image_base64 null. Depois: DELETE /jobs/{job_id}/source.",
    imageTasks:
      "Nas rotas describe, task aceita <CAPTION>, <DETAILED_CAPTION> e <MORE_DETAILED_CAPTION>. As rotas analyze aceitam as 15 tarefas do catálogo abaixo. Em curl use --form-string: -F interpreta < como leitura de arquivo. A tarefa padrão de descrição é configurável por VISION_CAPTION_TASK.",
    imageResponse:
      "Describe/OCR e analyze single com wait=true (200): job_id, status=completed, project, folder, image_base64 (eco dos bytes originais), image_mime_type, image_bytes, image_sha256, width, height, model (model_id, revision, device, dtype) e duration_ms, além da descrição ou do OCR. duration_ms mede o processamento reportado pelo worker; não é o tempo total da requisição.",
    ocrNote:
      "Cada linha tem text, quad_box=[x1,y1,x2,y2,x3,y3,x4,y4] e bbox=[x_min,y_min,x_max,y_max], em pixels da imagem original. Imagem sem texto retorna 200, text vazio e lines=[]. O exemplo abaixo mostra apenas os campos de OCR.",
    timeoutTitle: "Timeout e limites atuais",
    timeout:
      "Um 504 VISION_TIMEOUT traz detail.job_id, poll_url e result_url; a task continua. Consulte o mesmo job, sem reenviar a imagem. /jobs/{id}/result (ou ?format=json) retorna markdown, metadata e image, incluindo tarefa/configuração, imagem original, texto e regiões. Prefira wait=false para acompanhar a fila sem manter a conexão aberta.",
    formatTitle: "Formato da resposta: JSON (padrão) ou Markdown",
    formatIntro:
      "JSON é o padrão em todas as rotas de imagem e no resultado do job: se você não enviar nada, recebe o JSON de sempre, sem nenhuma mudança. Markdown é opcional e precisa ser pedido explicitamente.",
    formatHead: ["Onde", "Sem enviar nada (padrão)", "Para receber Markdown", "Para pedir JSON explicitamente"],
    formatRows: [
      ["Envio em JSON: /images/describe, /images/ocr, /images/analyze, /images/faces", "JSON", "\"output_format\": \"markdown\" no corpo", "omita o campo ou \"output_format\": \"json\""],
      ["Envio multipart: as mesmas rotas com /upload", "JSON", "-F \"output_format=markdown\"", "omita o campo ou -F \"output_format=json\""],
      ["Leitura: GET /jobs/{job_id}/result", "o formato escolhido no envio (JSON se nada foi enviado)", "?format=markdown", "?format=json"],
      ["202 enfileirado, 504 timeout e erros", "sempre JSON", "sempre JSON", "sempre JSON"],
    ],
    formatJsonExample: "Padrão — sem output_format, a resposta é JSON:",
    formatMarkdownExample: "Opcional — com output_format=markdown, a resposta é text/markdown:",
    formatReadExample: "Ler o mesmo job nos dois formatos, a qualquer momento:",
    markdownTitle: "Detalhes da saída em Markdown",
    markdown:
      "As 8 rotas de envio aceitam output_format=json (padrão, corpo inalterado) ou markdown (campo JSON ou campo do formulário multipart; outro valor responde 422). Com markdown, o sucesso síncrono (describe/ocr; analyze e faces com wait=true) responde 200 text/markdown; charset=utf-8; 202 enfileirado, 504 e erros continuam JSON. O formato fica gravado no job e é o padrão de GET /jobs/{job_id}/result; ?format=json ou ?format=markdown escolhem na leitura (vtt/srt/txt num job de imagem: 422). Títulos em português; o texto do modelo vem como produzido e escapado; image_base64 nunca entra. describe: # Descrição da imagem e metadados; ocr: # Texto da imagem, uma linha por linha detectada (ou \"Nenhum texto detectado.\"); analyze: # rótulo da tarefa e tabela de regiões; full: descrição, OCR, detecções, rostos (v2) e estado de cada tarefa; faces: tabela de rostos com scores de expressão não calibrados. Em full/faces, output_format não entra na Idempotency-Key: repetir a chave com outro formato devolve o mesmo job, só renderizado no formato pedido.",
    retention:
      "MySQL guarda o status e a referência ao resultado privado no MinIO. O resultado completo inclui a imagem original e a configuração; Redis é um cache. O resultado continua consultável após F5 ou expirar o cache. Excluir o job remove seu resultado privado; o worker remove apenas o handoff temporário.",
    imageErrors:
      "Erros de visão geralmente usam detail={error_code,message,job_id}; erros de autenticação e validação podem ter outro formato. 413: tamanho; 422: base64, formato, task, pixels ou localização inválidos; 503 nas tarefas single: visão desabilitada, worker/modelo indisponível ou motor sem vaga (VISION_ENGINE_UNAVAILABLE, com Retry-After). /capabilities também responde 503 se a visão estiver desabilitada; worker ausente/ocupado com visão habilitada retorna 200 com reason/estado. Full aguarda capacidade dentro do prazo.",
  },
  en: {
    imagesIntro:
      "Florence-2 exposes 15 tasks for captioning, OCR, detection, grounding and segmentation. Use /images/analyze (JSON) or /images/analyze/upload (multipart): wait=false returns 202 with job_id; wait=true waits for inference. Existing description/OCR routes remain synchronous. /convert offers every task and option advertised in the catalog.",
    imagesHead: ["Endpoint", "Input / output"],
    imagesRows: [
      [
        "POST /images/analyze",
        "JSON: mode=single/full, image_base64, filename, options and location. Defaults to 202; wait=true waits.",
      ],
      [
        "POST /images/analyze/upload",
        "multipart: file, mode=single/full, JSON options and location. Defaults to 202; wait=true waits.",
      ],
      [
        "POST /images/{job_id}/cancel",
        "Full Analysis only: 202 while running; 200 when terminal. Preserves completed results.",
      ],
      [
        "POST /images/describe/upload",
        "multipart: file, optional task, tags, project/project_id and folder/folder_id. Returns description and task.",
      ],
      [
        "POST /images/describe",
        "JSON: image_base64, optional filename, task, tags as an array and location. Same description response.",
      ],
      [
        "POST /images/ocr/upload",
        "multipart: file, tags and location. Returns text and lines[].",
      ],
      [
        "POST /images/ocr",
        "JSON: image_base64, optional filename, tags as an array and location. Same OCR; no task parameter.",
      ],
      [
        "GET /images/capabilities",
        "Worker state: dependencies_installed, model_downloaded, model_loaded, device_resolved, reason; tasks[], generation_schema/defaults, analysis_modes, full_profile and full_limits. Authenticated; does not start inference.",
      ],
    ],
    imageOptions:
      "PNG, JPEG, WEBP, BMP, GIF and TIFF, detected from their bytes. Default limits: 10 MB of decoded image data and 50 million pixels (VISION_MAX_IMAGE_SIZE_MB / VISION_MAX_IMAGE_PIXELS). Base64 accepts a data:image/...;base64, prefix and line breaks. Projects are required unless the API key is project-bound. JSON uses a tags array; multipart accepts comma-separated tags. Repeated single-mode submissions create new jobs; Full Analysis uses Idempotency-Key. purge_source (default false) exists on all 8 submission routes (describe, ocr and analyze, JSON and /upload; faces and faces/upload): true deletes every stored copy of the original image when the job finishes (completed, or failed/partial/cancelled; image routes have no automatic retry) — the local copy, the original and the normalized preview of full/face analysis in storage, and image.image_base64 of the stored result becomes null. The inference result (caption, OCR, regions, faces, markdown) stays. With wait=true, describe/ocr and single analyze still echo image_base64 at the top of the response (from this request's bytes, not a stored copy); Full and faces return image.image_base64 null. Later: DELETE /jobs/{job_id}/source.",
    imageTasks:
      "describe routes accept <CAPTION>, <DETAILED_CAPTION> and <MORE_DETAILED_CAPTION>. analyze routes accept all 15 tasks below. Use curl --form-string: -F treats a leading < as a file read. The default caption task is configurable with VISION_CAPTION_TASK.",
    imageResponse:
      "Describe/OCR and single analyze with wait=true (200): job_id, status=completed, project, folder, image_base64 (echo of the original bytes), image_mime_type, image_bytes, image_sha256, width, height, model (model_id, revision, device, dtype) and duration_ms, plus the description or OCR. duration_ms is processing time reported by the worker, not total request time.",
    ocrNote:
      "Every line has text, quad_box=[x1,y1,x2,y2,x3,y3,x4,y4] and bbox=[x_min,y_min,x_max,y_max], in original image pixels. Images without text return 200 with empty text and lines=[]. The example below shows only OCR fields.",
    timeoutTitle: "Timeout and current limitations",
    timeout:
      "A 504 VISION_TIMEOUT includes detail.job_id, poll_url and result_url; the task continues. Follow that job instead of uploading again. /jobs/{id}/result (or ?format=json) returns markdown, metadata and image, including the task/settings, original image, text and regions. Prefer wait=false to follow the queue without keeping the connection open.",
    formatTitle: "Response format: JSON (default) or Markdown",
    formatIntro:
      "JSON is the default on every image route and on the job result: if you send nothing, you get the same JSON as always, unchanged. Markdown is optional and must be requested explicitly.",
    formatHead: ["Where", "Sending nothing (default)", "To get Markdown", "To ask for JSON explicitly"],
    formatRows: [
      ["JSON requests: /images/describe, /images/ocr, /images/analyze, /images/faces", "JSON", "\"output_format\": \"markdown\" in the body", "omit the field or \"output_format\": \"json\""],
      ["Multipart requests: the same routes with /upload", "JSON", "-F \"output_format=markdown\"", "omit the field or -F \"output_format=json\""],
      ["Reading: GET /jobs/{job_id}/result", "the format chosen at submission (JSON if none was sent)", "?format=markdown", "?format=json"],
      ["202 queued, 504 timeout and errors", "always JSON", "always JSON", "always JSON"],
    ],
    formatJsonExample: "Default — without output_format the response is JSON:",
    formatMarkdownExample: "Optional — with output_format=markdown the response is text/markdown:",
    formatReadExample: "Read the same job in either format, at any time:",
    markdownTitle: "Markdown output details",
    markdown:
      "All 8 submission routes accept output_format=json (default, unchanged body) or markdown (a JSON field or a multipart form field; any other value returns 422). With markdown, a synchronous success (describe/ocr; analyze and faces with wait=true) returns 200 text/markdown; charset=utf-8; a queued 202, a 504 and errors stay JSON. The format is stored on the job and is the default of GET /jobs/{job_id}/result; ?format=json or ?format=markdown choose at read time (vtt/srt/txt on an image job: 422). Headings are in Portuguese; model text is kept as produced and escaped; image_base64 is never included. describe: # Descrição da imagem plus metadata; ocr: # Texto da imagem, one line per detected line (or \"Nenhum texto detectado.\"); analyze: # task label and a regions table; full: caption, OCR, detections, faces (v2) and the state of every task; faces: a faces table with uncalibrated expression scores. For full/faces, output_format is not part of the Idempotency-Key: replaying the key with another format returns the same job, rendered in the requested format.",
    retention:
      "MySQL stores status and a reference to the private MinIO result. The full result includes the original image and settings; Redis is a cache. Results remain available after reload or cache expiry. Deleting the job removes its private result; the worker only removes the temporary handoff.",
    imageErrors:
      "Vision errors generally use detail={error_code,message,job_id}; authentication and validation errors may differ. 413: size; 422: invalid base64, format, task, pixels or location; 503 on single tasks: vision disabled, unavailable worker/model or no engine capacity (VISION_ENGINE_UNAVAILABLE, with Retry-After). /capabilities also returns 503 when vision is disabled; an absent/busy worker with vision enabled returns 200 with reason/state. Full waits for capacity within its deadline.",
  },
};
