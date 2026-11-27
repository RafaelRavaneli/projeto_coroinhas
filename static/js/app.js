// Interações da interface: menu, diálogos, confirmações, cópia, busca e atalhos de período.
(function () {
  'use strict';

  // Menu do celular
  var menuBtn = document.querySelector('[data-menu-toggle]');
  var nav = document.getElementById('nav');
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () {
      var open = nav.classList.toggle('is-open');
      menuBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      menuBtn.setAttribute('aria-label', open ? 'Fechar menu' : 'Abrir menu');
    });
  }

  // Diálogos: <button data-open="id"> abre <dialog id="id">
  document.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-open]');
    if (opener) {
      var dialog = document.getElementById(opener.getAttribute('data-open'));
      if (dialog && typeof dialog.showModal === 'function') {
        closeMenus();
        dialog.showModal();
        var first = dialog.querySelector('[autofocus], input:not([type=hidden]), select, textarea');
        if (first && window.matchMedia('(pointer: fine)').matches) first.focus();
      }
      return;
    }
    var closer = event.target.closest('[data-close]');
    if (closer) {
      var parent = closer.closest('dialog');
      if (parent) parent.close();
      return;
    }
    // Clique no fundo escuro fecha o diálogo
    if (event.target.tagName === 'DIALOG' && event.target.open) {
      var rect = event.target.getBoundingClientRect();
      var inside = event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
      if (!inside) event.target.close();
    }
    // Clique fora fecha menus de ações
    if (!event.target.closest('details.menu')) closeMenus();
  });

  function closeMenus(except) {
    document.querySelectorAll('details.menu[open]').forEach(function (d) {
      if (d !== except) d.removeAttribute('open');
    });
  }
  document.addEventListener('toggle', function (event) {
    if (event.target.matches && event.target.matches('details.menu') && event.target.open) closeMenus(event.target);
  }, true);
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') closeMenus();
  });

  // Confirmação antes de ações destrutivas: <form data-confirm="Mensagem">
  document.addEventListener('submit', function (event) {
    var form = event.target;
    var message = form.getAttribute('data-confirm');
    if (message && !window.confirm(message)) {
      event.preventDefault();
      return;
    }
    var button = form.querySelector('[type=submit][data-busy]');
    if (button) {
      var label = button.querySelector('[data-label]');
      if (label) label.textContent = button.getAttribute('data-busy');
      button.setAttribute('aria-busy', 'true');
      setTimeout(function () { button.disabled = true; }, 0);
    }
  });

  // Copiar texto: <button data-copy="idDoCampo">
  document.querySelectorAll('[data-copy]').forEach(function (button) {
    button.addEventListener('click', function () {
      var field = document.getElementById(button.getAttribute('data-copy'));
      if (!field) return;
      var original = button.textContent;
      var done = function () {
        button.textContent = 'Mensagem copiada';
        setTimeout(function () { button.textContent = original; }, 2000);
      };
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(field.value).then(done);
      } else {
        field.select();
        document.execCommand('copy');
        done();
      }
    });
  });

  // Busca na tabela: <input data-search="idDaTabela">
  document.querySelectorAll('[data-search]').forEach(function (input) {
    var table = document.getElementById(input.getAttribute('data-search'));
    if (!table) return;
    var rows = Array.prototype.slice.call(table.querySelectorAll('tbody tr[data-text]'));
    var empty = table.querySelector('[data-search-empty]');
    var normalize = function (s) { return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); };
    input.addEventListener('input', function () {
      var term = normalize(input.value.trim());
      var shown = 0;
      rows.forEach(function (row) {
        var match = !term || normalize(row.getAttribute('data-text')).indexOf(term) !== -1;
        row.hidden = !match;
        if (match) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
    });
  });

  // Restrição por horário exato: mostra o campo de horário só quando "Só um horário" é escolhido
  document.querySelectorAll('select[data-periodo]').forEach(function (select) {
    var campo = select.form && select.form.querySelector('[data-horario]');
    if (!campo) return;
    var atualizar = function () {
      var ativo = select.value === 'Horário';
      campo.hidden = !ativo;
      campo.disabled = !ativo;
      campo.required = ativo;
      if (ativo && document.activeElement === select) campo.focus();
    };
    select.addEventListener('change', atualizar);
    atualizar();
  });

  // Atalhos de período: <button data-range="weekend|two-weeks|month" data-form="idDoForm">
  function iso(d) {
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return d.getFullYear() + '-' + m + '-' + day;
  }
  document.querySelectorAll('[data-range]').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var form = document.getElementById(chip.getAttribute('data-form'));
      if (!form) return;
      var today = new Date();
      today.setHours(0, 0, 0, 0);
      var start = new Date(today);
      var end = new Date(today);
      var range = chip.getAttribute('data-range');
      if (range === 'weekend') {
        var toSaturday = (6 - today.getDay() + 7) % 7;
        if (today.getDay() === 0) toSaturday = -1;
        start.setDate(today.getDate() + toSaturday);
        end = new Date(start);
        end.setDate(start.getDate() + 1);
      } else if (range === 'two-weeks') {
        end.setDate(today.getDate() + 14);
      } else if (range === 'month') {
        start = new Date(today.getFullYear(), today.getMonth(), 1);
        end = new Date(today.getFullYear(), today.getMonth() + 1, 0);
      }
      form.querySelector('[name=data_inicio]').value = iso(start);
      form.querySelector('[name=data_fim]').value = iso(end);
      form.submit();
    });
  });
})();
