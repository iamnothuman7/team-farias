"""Grupos compartilhados pelo formulário de configurações."""
CONFIGURATION_GROUPS = [
    ("Marca e aparência", ["name", "tagline", "logo_url", "accent_color"]),
    ("Contatos e localização", ["whatsapp", "phone", "instagram", "email", "city", "state", "address"]),
    ("Página inicial", ["hero_title", "hero_highlight", "hero_description", "meta_description", "about_title", "about_text", "footer_text"]),
    ("Convite e consulta de planos", ["plan_title", "plan_description", "cta_title", "cta_text", "whatsapp_label"]),
    ("Seções visíveis", ["show_about", "show_system", "show_steps", "show_groups", "show_stats", "show_next_session", "auto_install_prompt"]),
    ("Matrícula e pagamento", ["minimum_age", "pix"]),
]
