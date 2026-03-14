def fix_css():
    with open('app/static/index.html', 'r', encoding='utf-8') as f:
        text = f.read()

    old_css = '''    /* ── Responsive ────────────────────────────────────────── */
    @media (max-width: 700px) {
      .filters {
        flex-direction: column;
        align-items: stretch;
      }

      .stats {
        grid-template-columns: repeat(2, 1fr);
      }

      thead th:nth-child(4),
      tbody td:nth-child(4),
      thead th:nth-child(5),
      tbody td:nth-child(5) {
        display: none;
      }
    }'''

    new_css = '''    /* ── Responsive ────────────────────────────────────────── */
    @media (max-width: 700px) {
      .filters {
        flex-direction: column;
        align-items: stretch;
      }

      .stats {
        grid-template-columns: repeat(2, 1fr);
      }

      .table-wrap {
        overflow-x: auto;
      }
      
      table {
        min-width: 600px;
      }
    }'''

    text = text.replace(old_css, new_css)
    with open('app/static/index.html', 'w', encoding='utf-8') as f:
        f.write(text)
fix_css()
