// Interações de Interface (UI) - Guia do Turista Inteligente

/**
 * Alterna a visibilidade dos detalhes do cartão (Accordion)
 * @param {string} id - Identificador do cartão de viagem
 * @param {Event} event - Evento de clique
 */
function alternarCard(id, event) {
  // Ignora se o clique veio de botões de ação ou links
  if (event && event.target && event.target.closest(".btn-actions, .btn, button, a, form, input")) {
    return;
  }

  const container = document.getElementById(`detalhes-${id}`);
  const indicador = document.getElementById(`indicador-${id}`);
  if (!container) return;

  const estaOculto = container.classList.contains("hidden");
  if (estaOculto) {
    container.classList.remove("hidden");
    if (indicador) {
      indicador.innerText = "▲";
      indicador.classList.add("ativo");
    }
  } else {
    container.classList.add("hidden");
    if (indicador) {
      indicador.innerText = "▼";
      indicador.classList.remove("ativo");
    }
  }
}

/**
 * ========================================================
 * SISTEMA DE TOAST / NOTIFICAÇÕES FLUTUANTES
 * ========================================================
 */

/**
 * Fecha uma notificação toast com animação suave de saída
 * @param {HTMLElement} elemento - Botão de fechar ou elemento interno do toast
 */
function fecharToast(elemento) {
  if (!elemento) return;
  const toast = elemento.closest(".toast");
  if (toast) {
    toast.classList.add("toast-saindo");
    setTimeout(function () {
      if (toast && toast.parentNode) {
        toast.remove();
      }
    }, 300);
  }
}

/**
 * Exibe programaticamente uma notificação toast flutuante
 * @param {string} mensagem - Texto principal da notificação
 * @param {string} tipo - Categoria ('erro', 'sucesso', 'info')
 * @param {string} titulo - Título customizado opcional
 */
function mostrarToast(mensagem, tipo = "erro", titulo = "") {
  let container = document.getElementById("toastContainer");
  if (!container) {
    container = document.createElement("div");
    container.id = "toastContainer";
    container.className = "toast-container";
    container.setAttribute("aria-live", "polite");
    container.setAttribute("aria-atomic", "true");
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${tipo} flash-alert flash-${tipo}`;
  toast.setAttribute("role", "alert");

  let icone = "ℹ️";
  let tituloPadrao = titulo;

  if (tipo === "erro" || tipo === "error" || tipo === "danger") {
    icone = "⚠️";
    if (!tituloPadrao) tituloPadrao = "Falha na Requisição";
  } else if (tipo === "sucesso" || tipo === "success") {
    icone = "✅";
    if (!tituloPadrao) tituloPadrao = "Sucesso";
  } else {
    icone = "ℹ️";
    if (!tituloPadrao) tituloPadrao = "Aviso";
  }

  toast.innerHTML = `
    <div class="toast-icon">${icone}</div>
    <div class="toast-body">
      <div class="toast-title">${tituloPadrao}</div>
      <div class="toast-message">${mensagem}</div>
    </div>
    <button type="button" class="toast-close" onclick="fecharToast(this)" aria-label="Fechar notificação">&times;</button>
  `;

  container.appendChild(toast);

  // Auto-dismiss após 6 segundos
  setTimeout(function () {
    if (toast && toast.isConnected) {
      const btnClose = toast.querySelector(".toast-close");
      fecharToast(btnClose || toast);
    }
  }, 6000);
}

// Expõe globalmente para fácil acesso e testes
window.mostrarToast = mostrarToast;
window.fecharToast = fecharToast;

/**
 * ========================================================
 * ESTADO DE CARREGAMENTO & DEMONSTRAÇÃO DE IDEMPOTÊNCIA
 * O botão permanece clicável durante o carregamento para
 * demonstrar que cliques repetidos não duplicam registros.
 * ========================================================
 */
let carregando = false;
let contadorCliques = 0;
let timerSeguranca = null;

/**
 * Exibe o card de carregamento com animação e rota informada pelo usuário
 */
function exibirCardLoading(origem, destino) {
  const cardLoading = document.getElementById("cardLoading");
  if (!cardLoading) return;

  const rotaTexto = document.getElementById("loadingRotaTexto");
  if (rotaTexto) {
    rotaTexto.innerHTML = `${origem} <span class="viagem-rota-seta">➔</span> ${destino}`;
  }

  cardLoading.classList.remove("hidden");

  const msgVazia = document.getElementById("msgSemRoteiros");
  if (msgVazia) {
    msgVazia.style.display = "none";
  }

  // Rolagem suave para o card de carregamento
  try {
    cardLoading.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (_) {
    // Ignora erro de scroll em navegadores mais antigos
  }
}

/**
 * Oculta o card de carregamento
 */
function ocultarCardLoading() {
  const cardLoading = document.getElementById("cardLoading");
  if (cardLoading) {
    cardLoading.classList.add("hidden");
  }
  const msgVazia = document.getElementById("msgSemRoteiros");
  if (msgVazia) {
    msgVazia.style.display = "";
  }
}

/**
 * Restaura o botão e o formulário para o estado inicial
 */
function resetarEstadoBotao() {
  carregando = false;
  contadorCliques = 0;
  if (timerSeguranca) {
    clearTimeout(timerSeguranca);
    timerSeguranca = null;
  }
  const btn = document.getElementById("btnGerarGuia");
  if (btn) {
    btn.disabled = false;
    btn.classList.remove("btn-loading");
    btn.innerText = "Gerar Guia com APIs & IA (Python)";
    btn.style.opacity = "1";
    btn.style.cursor = "pointer";
  }

  const form = document.getElementById("formCriarViagem");
  if (form) {
    const inputs = form.querySelectorAll("input, select");
    inputs.forEach(function (campo) {
      campo.removeAttribute("readonly");
      campo.style.pointerEvents = "";
    });
  }

  ocultarCardLoading();
}

// Garante que o botão e o card sejam liberados em caso de restauração de cache (BFCache / Navegação)
window.addEventListener("pageshow", resetarEstadoBotao);
window.addEventListener("load", resetarEstadoBotao);

document.addEventListener("DOMContentLoaded", function () {
  // 1. Inicializa auto-dismiss para toasts renderizados pelo servidor
  const toastsIniciais = document.querySelectorAll(".toast");
  toastsIniciais.forEach(function (toast) {
    setTimeout(function () {
      if (toast && toast.isConnected) {
        const btnClose = toast.querySelector(".toast-close");
        fecharToast(btnClose || toast);
      }
    }, 6000);
  });

  // 2. Configuração do formulário de criação com suporte a múltiplos cliques (Idempotência)
  const form = document.getElementById("formCriarViagem");
  const btn = document.getElementById("btnGerarGuia");

  if (form && btn) {
    form.addEventListener("submit", async function (e) {
      e.preventDefault();

      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }

      contadorCliques++;

      // Se já está em carregamento, o botão PERMANECE CLICÁVEL para demonstrar idempotência
      if (carregando) {
        btn.innerHTML = `<span class="spinner-btn"></span> Consultando APIs e Gemini AI... (${contadorCliques} cliques - idempotência ativa)`;

        // Dispara requisição duplicada em segundo plano para o backend acionar o lock de idempotência
        const formDataDuplicada = new FormData(form);
        fetch(form.action, {
          method: "POST",
          body: formDataDuplicada,
        }).catch(function (_) {
          // Ignora rejeição de rede em requisições concorrentes de teste
        });
        return;
      }

      // Primeiro clique: ativa o estado de carregamento mantendo o botão clicável
      carregando = true;
      btn.disabled = false; // Permanece clicável para permitir cliques múltiplos
      btn.classList.add("btn-loading");
      btn.style.cursor = "pointer";
      btn.innerHTML = '<span class="spinner-btn"></span> Consultando APIs e Gemini AI...';

      // Captura valores digitados para alimentar o card de loading
      const origemCidade = document.getElementById("origem_cidade")
        ? document.getElementById("origem_cidade").value.trim()
        : "";
      const origemUf = document.getElementById("origem_uf")
        ? document.getElementById("origem_uf").value.trim()
        : "";
      const destinoCidade = document.getElementById("destino_cidade")
        ? document.getElementById("destino_cidade").value.trim()
        : "";
      const destinoUf = document.getElementById("destino_uf")
        ? document.getElementById("destino_uf").value.trim()
        : "";

      const origemFmt = origemUf ? `${origemCidade} - ${origemUf}` : origemCidade;
      const destinoFmt = destinoUf ? `${destinoCidade} - ${destinoUf}` : destinoCidade;

      exibirCardLoading(origemFmt || "Origem", destinoFmt || "Destino");

      // Protege os campos contra edição enquanto processa para manter coerência da idempotência
      const inputs = form.querySelectorAll("input, select");
      inputs.forEach(function (campo) {
        campo.setAttribute("readonly", "true");
        campo.style.pointerEvents = "none";
      });

      // Timer de segurança de 60s
      timerSeguranca = setTimeout(function () {
        resetarEstadoBotao();
      }, 60000);

      const formDataPrincipal = new FormData(form);

      try {
        const resposta = await fetch(form.action, {
          method: "POST",
          body: formDataPrincipal,
        });

        const html = await resposta.text();
        const parser = new DOMParser();
        const docNovo = parser.parseFromString(html, "text/html");

        // Atualiza a lista de viagens com o novo card gerado
        const listaNova = docNovo.getElementById("listaViagens");
        const listaAtual = document.getElementById("listaViagens");
        if (listaNova && listaAtual) {
          listaAtual.innerHTML = listaNova.innerHTML;
        }

        // Renderiza eventuais novos toasts de erro (ex: timeout do Gemini)
        const novosToasts = docNovo.querySelectorAll("#toastContainer .toast");
        const containerToast = document.getElementById("toastContainer");
        if (novosToasts && containerToast) {
          novosToasts.forEach(function (toastEl) {
            containerToast.appendChild(toastEl);
            setTimeout(function () {
              if (toastEl && toastEl.isConnected) {
                const btnClose = toastEl.querySelector(".toast-close");
                fecharToast(btnClose || toastEl);
              }
            }, 6000);
          });
        }

        // Limpa formulário e restaura botão
        form.reset();
        resetarEstadoBotao();

        // Se por algum motivo o container não estava presente, realiza substituição limpa
        if (!listaNova || !listaAtual) {
          document.open();
          document.write(html);
          document.close();
        }
      } catch (err) {
        console.error("Erro na comunicação com o servidor:", err);
        resetarEstadoBotao();
        mostrarToast("Falha de conexão ao gerar o roteiro. Tente novamente.", "erro");
      }
    });
  }
});
