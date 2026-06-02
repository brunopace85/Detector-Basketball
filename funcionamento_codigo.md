# Funcionamento do Código — Etapa por Etapa

Este documento explica de forma detalhada o fluxo lógico de processamento de imagens e vídeos no script `roboflow_inferencia.py`, focando apenas na lógica de visão computacional e comunicação com a API (excluindo a interface gráfica Tkinter).

---

## 📋 Sumário do Fluxo
1. **Conversão de Imagem para Base64**
2. **Chamada à API do Roboflow**
3. **Extração das Predições (JSON)**
4. **Desenho das Caixas de Detecção (Bounding Boxes)**
5. **Processamento de Imagens Estáticas**
6. **Processamento de Vídeos (Frame-a-Frame com Otimização)**
7. **Exibição Interativa dos Resultados**

---

### 1. Conversão de Imagem para Base64
A função `imagem_para_base64` prepara a imagem para envio. A API do Roboflow espera receber a imagem codificada em texto Base64 no corpo da requisição.

* **Se um caminho de arquivo for passado (`caminho`):** Abre a imagem no disco em modo binário de leitura (`rb`), codifica os bytes em Base64 e os decodifica para uma string UTF-8.
* **Se uma imagem na memória for passada (`frame_cv2`):** É o caso do processamento de vídeo. O OpenCV codifica o frame (matriz de pixels) como um arquivo temporário do tipo JPEG na memória usando `cv2.imencode`, convertendo-o em seguida para a string Base64.

---

### 2. Chamada à API do Roboflow
A função `chamar_api` envia o payload à API Serverless do Roboflow usando o método HTTP `POST`.

* **Endpoint**: A URL é formada dinamicamente contendo o `MODEL_ID` (`basketball-lhqoe`), a `VERSION` (`1`) e o parâmetro de autenticação `api_key`.
* **Payload**: O conteúdo em Base64 da imagem é enviado diretamente no corpo da requisição (`data=img_b64`).
* **Headers**: Define o `Content-Type` como `application/x-www-form-urlencoded`.

---

### 3. Extração das Predições
A função `extrair_predicoes` recebe a resposta JSON bruta da API e a limpa para retornar uma lista simples de detecções.

* A API retorna um dicionário que contém a chave `predictions`. A função busca e extrai essa lista.
* Ela possui uma lógica de contingência (fallback): caso a resposta venha no formato de Workflows (onde a resposta fica encapsulada em `outputs[0]['model_output']['predictions']`), a função navega por essa estrutura sem quebrar o código.

---

### 4. Desenho das Caixas de Detecção (Bounding Boxes)
A função `desenhar_frame` pega um frame (imagem do OpenCV) e desenha retângulos e textos contendo a classe do objeto e a confiança da detecção.

1. **Conversão de Coordenadas**: O Roboflow retorna a caixa de detecção no formato centralizado `(x, y, width, height)`, onde `(x, y)` é o ponto central. O OpenCV precisa de pontos de cantos extremos `(x1, y1)` e `(x2, y2)`. O cálculo é:
   - $x_1 = x - \frac{w}{2}$
   - $y_1 = y - \frac{h}{2}$
   - $x_2 = x + \frac{w}{2}$
   - $y_2 = y + \frac{h}{2}$
2. **Desenho**:
   - `cv2.rectangle`: Desenha a borda da caixa ao redor do objeto (bola ou cesta).
   - `cv2.rectangle` (com espessura `-1`): Cria uma caixa sólida de fundo onde o texto da classe e confiança será exibido (evitando que o texto fique ilegível por causa do fundo).
   - `cv2.putText`: Escreve a legenda (ex: "Basketball Hoop 99%") no topo da caixa.

---

### 5. Processamento de Imagens Estáticas
A função `processar_imagem` coordena o fluxo de ponta a ponta para uma única foto:

1. Executa a codificação Base64.
2. Faz a chamada `POST` à API.
3. Se a API responder com sucesso (Status 200), o JSON da resposta é salvo no arquivo `resultado.json`.
4. Extrai a lista de predições.
5. Se houver predições com confiança maior que o limite configurado (`CONFIANCA_MIN`), o OpenCV lê a imagem original com `cv2.imread`, desenha as caixas e salva a nova imagem em disco com o nome `resultado_deteccao.jpg`.

---

### 6. Processamento de Vídeos (Frame-a-Frame com Otimização)
A função `processar_video` realiza a leitura sequencial do arquivo de vídeo. Como vídeos contêm muitos frames (geralmente 30 por segundo), enviar todos os frames causaria lentidão e alto consumo de API. Há uma estratégia de otimização implementada:

1. **Leitura e Escrita do Vídeo**: O OpenCV abre o vídeo (`cv2.VideoCapture`) e cria um arquivo de saída (`cv2.VideoWriter`) configurado com a mesma taxa de quadros (FPS) e dimensões.
2. **Intervalo de Frames (`FRAME_INTERVAL`)**:
   - O código processa e envia frames para a API do Roboflow **apenas** a cada `FRAME_INTERVAL` frames (por exemplo, de 5 em 5 quadros).
   - Para os frames intermediários que são pulados, o OpenCV desenha as caixas utilizando a **última predição conhecida** (`ultima_pred`). Isso mantém a fluidez visual no vídeo final sem a necessidade de enviar requisições duplicadas.
3. **Escrita**: Cada frame editado com as bounding boxes é gravado no vídeo gerado (`resultado_video.mp4`).

---

### 7. Exibição Interativa dos Resultados
As funções `abrir_imagem_resultado` e `abrir_video_resultado` lidam com a renderização em tempo de execução:

* **Janela Redimensionável**: Cria a janela utilizando `cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)`. Isso permite ao usuário alterar o tamanho da janela arrastando os cantos, escalando a imagem ou vídeo dinamicamente.
* **Espera e Destruição**:
   - Imagens: Abrem e esperam indefinidamente (`cv2.waitKey(0)`) até qualquer tecla ser pressionada.
   - Vídeos: São exibidos frame a frame a cada 30 milissegundos (`cv2.waitKey(30)`). Se o usuário pressionar a tecla **Q**, o loop é quebrado.
* **Limpeza**: Após o encerramento da exibição, os arquivos temporários gerados em disco (`resultado_deteccao.jpg` ou `resultado_video.mp4`) são apagados com `os.remove` para poupar espaço.
