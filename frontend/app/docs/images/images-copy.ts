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
      "Um 504 VISION_TIMEOUT traz detail.job_id, poll_url e result_url; a task continua. Consulte o mesmo job, sem reenviar a imagem. /jobs/{id}/result?format=markdown retorna markdown, metadata e image, incluindo tarefa/configuração, imagem original, texto e regiões. Prefira wait=false para acompanhar a fila sem manter a conexão aberta.",
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
      "A 504 VISION_TIMEOUT includes detail.job_id, poll_url and result_url; the task continues. Follow that job instead of uploading again. /jobs/{id}/result?format=markdown returns markdown, metadata and image, including the task/settings, original image, text and regions. Prefer wait=false to follow the queue without keeping the connection open.",
    retention:
      "MySQL stores status and a reference to the private MinIO result. The full result includes the original image and settings; Redis is a cache. Results remain available after reload or cache expiry. Deleting the job removes its private result; the worker only removes the temporary handoff.",
    imageErrors:
      "Vision errors generally use detail={error_code,message,job_id}; authentication and validation errors may differ. 413: size; 422: invalid base64, format, task, pixels or location; 503 on single tasks: vision disabled, unavailable worker/model or no engine capacity (VISION_ENGINE_UNAVAILABLE, with Retry-After). /capabilities also returns 503 when vision is disabled; an absent/busy worker with vision enabled returns 200 with reason/state. Full waits for capacity within its deadline.",
  },
};
