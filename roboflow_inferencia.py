

import requests
import json
import os
import sys
import base64
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import cv2
import tempfile

API_KEY        = os.getenv("ROBOFLOW_API_KEY", "vJHHKKfi3R2T7aLWtRm1")
MODEL_ID       = "basketball-lhqoe"
VERSION        = "1"
CONFIANCA_MIN  = 0.3

FRAME_INTERVAL = 5



def imagem_para_base64(frame_cv2=None, caminho=None):
    if caminho:
        with open(caminho, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    _, buffer = cv2.imencode(".jpg", frame_cv2)
    return base64.b64encode(buffer).decode("utf-8")


def chamar_api(img_b64):
    url = f"https://detect.roboflow.com/{MODEL_ID}/{VERSION}?api_key={API_KEY}"
    response = requests.post(
        url,
        data=img_b64,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    return response


def extrair_predicoes(data):
    try:
        if not isinstance(data, dict):
            return []
        if "predictions" in data:
            return data["predictions"]
        outputs = data.get("outputs", [{}])
        model_output = outputs[0] if outputs else {}
        predicoes = model_output.get("model_output", [])
        if isinstance(predicoes, dict):
            predicoes = predicoes.get("predictions", [])
        return predicoes or []
    except Exception:
        return []


def desenhar_frame(frame, predicoes):
    cores = [(0,255,0),(255,100,0),(0,100,255),(255,255,0),(0,255,255)]
    count = 0
    for i, det in enumerate(predicoes):
        if det.get("confidence", 0) < CONFIANCA_MIN:
            continue
        count += 1
        classe = det.get("class", "?")
        conf   = det.get("confidence", 0) * 100
        cx, cy = int(det.get("x", 0)), int(det.get("y", 0))
        w, h   = int(det.get("width", 0)), int(det.get("height", 0))
        x1, y1 = cx - w//2, cy - h//2
        x2, y2 = cx + w//2, cy + h//2
        cor = cores[i % len(cores)]
        cv2.rectangle(frame, (x1,y1), (x2,y2), cor, 2)
        label = f"{classe} {conf:.0f}%"
        (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(frame, (x1, y1-lh-8), (x1+lw+4, y1), cor, -1)
        cv2.putText(frame, label, (x1+2, y1-4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)
    return frame, count



def processar_imagem(caminho, callback_status):
    callback_status("Enviando imagem para o Roboflow...")
    img_b64 = imagem_para_base64(caminho=caminho)
    response = chamar_api(img_b64)

    if response.status_code != 200:
        raise Exception(f"Erro {response.status_code}: {response.text[:120]}")

    data = response.json()
    with open("resultado.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    predicoes = extrair_predicoes(data)
    if not predicoes:
        return 0, None

    frame = cv2.imread(caminho)
    frame, count = desenhar_frame(frame, predicoes)
    saida = "resultado_deteccao.jpg"
    cv2.imwrite(saida, frame)
    return count, saida


def abrir_imagem_resultado(saida):
    img = cv2.imread(saida)
    window_name = "Resultado — Detecção de Basquete"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.imshow(window_name, img)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    os.remove(saida)



def processar_video(caminho, callback_status, callback_progresso):
    cap = cv2.VideoCapture(caminho)
    if not cap.isOpened():
        raise Exception("Não foi possível abrir o vídeo.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps          = cap.get(cv2.CAP_PROP_FPS) or 25
    largura      = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    altura       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    saida = "resultado_video.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(saida, fourcc, fps, (largura, altura))

    frame_idx      = 0
    total_detec    = 0
    ultima_pred    = []  

    callback_status(f"Processando vídeo — 0 / {total_frames} frames...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % FRAME_INTERVAL == 0:
            img_b64 = imagem_para_base64(frame_cv2=frame)
            try:
                response = chamar_api(img_b64)
                if response.status_code == 200:
                    data = response.json()
                    ultima_pred = extrair_predicoes(data)
            except Exception:
                pass

        frame, count = desenhar_frame(frame, ultima_pred)
        total_detec += count
        writer.write(frame)

        frame_idx += 1
        pct = int(frame_idx / total_frames * 100) if total_frames > 0 else 0
        callback_status(f"Processando — frame {frame_idx}/{total_frames} ({pct}%)")
        callback_progresso(pct)

    cap.release()
    writer.release()
    return total_detec, saida, total_frames


def abrir_video_resultado(saida):
    cap = cv2.VideoCapture(saida)
    window_name = "Resultado — Detecção de Basquete (Q para sair)"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        cv2.imshow(window_name, frame)
        if cv2.waitKey(30) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    os.remove(saida)


# ============================================================
# INTERFACE GRÁFICA
# ============================================================

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Detector de Basquete")
        self.root.geometry("480x380")
        self.root.resizable(False, False)
        self.caminho = tk.StringVar(value="Nenhum arquivo selecionado")
        self.modo = tk.StringVar(value="imagem")
        self._build_ui()

    def _build_ui(self):
        tk.Label(self.root, text="🏀 Detector de Basquete",
                 font=("Segoe UI", 16, "bold")).pack(pady=(22,2))
        tk.Label(self.root, text="Roboflow · basketball-lhqoe/1",
                 font=("Segoe UI", 9), fg="gray").pack()

        ttk.Separator(self.root, orient="horizontal").pack(
            fill="x", padx=24, pady=14)

        # Tabs imagem / vídeo
        tab_frame = tk.Frame(self.root)
        tab_frame.pack(padx=24, fill="x")

        self.btn_tab_img = tk.Button(
            tab_frame, text="  Imagem", font=("Segoe UI", 9, "bold"),
            relief="flat", bg="#6c47ff", fg="white", cursor="hand2",
            padx=12, pady=4, command=lambda: self._set_modo("imagem"))
        self.btn_tab_img.pack(side="left", padx=(0,4))

        self.btn_tab_vid = tk.Button(
            tab_frame, text=" Vídeo", font=("Segoe UI", 9),
            relief="flat", bg="#e0e0e0", fg="#333", cursor="hand2",
            padx=12, pady=4, command=lambda: self._set_modo("video"))
        self.btn_tab_vid.pack(side="left")

        # Seleção de arquivo
        frame = tk.Frame(self.root)
        frame.pack(padx=24, fill="x", pady=(14,0))
        self.label_arquivo = tk.Label(
            frame, text="Imagem:", font=("Segoe UI", 10))
        self.label_arquivo.pack(anchor="w", pady=(0,4))

        row = tk.Frame(frame)
        row.pack(fill="x")
        tk.Entry(row, textvariable=self.caminho, state="readonly",
                 font=("Segoe UI", 9), relief="solid", bd=1).pack(
                     side="left", fill="x", expand=True)
        tk.Button(row, text=" Procurar", command=self.selecionar_arquivo,
                  font=("Segoe UI", 9), relief="solid", bd=1,
                  cursor="hand2").pack(side="left", padx=(6,0))

        # Info frame interval (só vídeo)
        self.info_video = tk.Label(
            frame,
            text=f"Intervalo entre análises: {FRAME_INTERVAL} frames  "
                 f"(ajuste FRAME_INTERVAL no script)",
            font=("Segoe UI", 8), fg="gray")

        ttk.Separator(self.root, orient="horizontal").pack(
            fill="x", padx=24, pady=14)

        self.btn = tk.Button(
            self.root, text=" Detectar Basquete",
            command=self.executar,
            font=("Segoe UI", 11, "bold"),
            bg="#6c47ff", fg="white",
            activebackground="#5235cc", activeforeground="white",
            relief="flat", cursor="hand2", padx=20, pady=8)
        self.btn.pack(pady=(0,10))

        self.status = tk.Label(self.root, text="",
                               font=("Segoe UI", 9), fg="gray")
        self.status.pack()

        self.progress_val = tk.IntVar(value=0)
        self.progress = ttk.Progressbar(
            self.root, mode="indeterminate", length=220)
        self.progress.pack(pady=(6,0))

        self.progress_det = ttk.Progressbar(
            self.root, variable=self.progress_val,
            maximum=100, length=220, mode="determinate")

    def _set_modo(self, modo):
        self.modo.set(modo)
        self.caminho.set("Nenhum arquivo selecionado")
        if modo == "imagem":
            self.btn_tab_img.config(bg="#6c47ff", fg="white",
                                    font=("Segoe UI", 9, "bold"))
            self.btn_tab_vid.config(bg="#e0e0e0", fg="#333",
                                    font=("Segoe UI", 9))
            self.label_arquivo.config(text="Imagem:")
            self.info_video.pack_forget()
            self.progress_det.pack_forget()
        else:
            self.btn_tab_vid.config(bg="#6c47ff", fg="white",
                                    font=("Segoe UI", 9, "bold"))
            self.btn_tab_img.config(bg="#e0e0e0", fg="#333",
                                    font=("Segoe UI", 9))
            self.label_arquivo.config(text="Vídeo:")
            self.info_video.pack(anchor="w", pady=(6,0))
            self.progress_det.pack(pady=(4,0))

    def selecionar_arquivo(self):
        if self.modo.get() == "imagem":
            tipos = [("Imagens", "*.jpg *.jpeg *.png *.bmp *.webp"),
                     ("Todos", "*.*")]
        else:
            tipos = [("Vídeos", "*.mp4 *.avi *.mov *.mkv *.wmv"),
                     ("Todos", "*.*")]
        path = filedialog.askopenfilename(title="Selecione o arquivo",
                                          filetypes=tipos)
        if path:
            self.caminho.set(path)
            self.status.config(text="Arquivo carregado. Clique em Detectar.")

    def executar(self):
        caminho = self.caminho.get()
        if not os.path.exists(caminho):
            messagebox.showwarning("Atenção", "Selecione um arquivo válido.")
            return
        threading.Thread(target=self._rodar, args=(caminho,), daemon=True).start()

    def _set_status(self, texto, cor="gray"):
        self.status.config(text=texto, fg=cor)

    def _set_progresso(self, valor):
        self.progress_val.set(valor)

    def _rodar(self, caminho):
        self.btn.config(state="disabled", text="Analisando...")
        self.progress.start(10)
        self.progress_val.set(0)

        try:
            if self.modo.get() == "imagem":
                count, saida = processar_imagem(caminho, self._set_status)
                self.progress.stop()

                if not saida:
                    self._set_status("Nenhum objeto detectado.", "orange")
                    messagebox.showinfo("Resultado", "Nenhum basquete ou cesta detectado.")
                    return

                self._set_status(f" {count} objeto(s) detectado(s) — abrindo resultado...", "green")
                abrir_imagem_resultado(saida)
                self._set_status(f" Concluído — {count} objeto(s) detectado(s).", "green")

            else:
                count, saida, total = processar_video(
                    caminho, self._set_status, self._set_progresso)
                self.progress.stop()

                if count == 0:
                    self._set_status("Nenhum objeto detectado no vídeo.", "orange")
                    messagebox.showinfo("Resultado", "Nenhum basquete ou cesta detectado.")
                    os.remove(saida)
                    return

                self._set_status(f" {total} frames processados — abrindo vídeo...", "green")
                abrir_video_resultado(saida)
                self._set_status("Concluído.", "green")

        except Exception as e:
            self.progress.stop()
            self._set_status(f"Erro: {e}", "red")
            messagebox.showerror("Erro", str(e))

        finally:
            self.btn.config(state="normal", text=" Detectar Basquete")


# ============================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
