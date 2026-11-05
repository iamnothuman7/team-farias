
from django.core.validators import RegexValidator, MaxValueValidator, URLValidator
from django.db import models
from django.urls import reverse


class Product(models.Model):
    name = models.CharField("nome do produto", max_length=120)
    description = models.TextField("descrição", max_length=3000, blank=True)
    category = models.CharField("categoria", max_length=40, default="Camisas")
    image = models.ImageField("foto do produto", upload_to="products/", blank=True)
    price = models.DecimalField("valor de referência (R$)", max_digits=9, decimal_places=2, null=True, blank=True, help_text="Deixe vazio para consultar pelo WhatsApp.")
    sizes = models.CharField("tamanhos disponíveis", max_length=250, blank=True, help_text="Separe por vírgula: PP, P, M, G, GG. Deixe vazio se não houver tamanho.")
    colors = models.CharField("cores disponíveis", max_length=350, blank=True, help_text="Separe por vírgula. Deixe vazio se houver uma única versão.")
    customize_name = models.BooleanField("pedir nome para estampar", default=False)
    customize_number = models.BooleanField("pedir número para estampar", default=False)
    order_enabled = models.BooleanField("aceitar pedidos", default=True)
    is_active = models.BooleanField("publicar no catálogo", default=False)
    position = models.PositiveSmallIntegerField("ordem de exibição", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "name", "pk"]
        verbose_name = "produto"
        verbose_name_plural = "produtos"
        constraints = [models.CheckConstraint(condition=models.Q(price__isnull=True) | models.Q(price__gte=0), name="product_nonnegative_price")]

    def __str__(self):
        return self.name

    @property
    def size_options(self):
        return [item.strip() for item in self.sizes.split(",") if item.strip()]

    @property
    def color_options(self):
        return [item.strip() for item in self.colors.split(",") if item.strip()]

    def get_absolute_url(self):
        return reverse("core:product", args=[self.pk])


class SiteConfiguration(models.Model):
    """Configuração única; conteúdo e regras de operação, nunca credenciais."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    name = models.CharField("nome da marca", max_length=80, default="Team Farias")
    tagline = models.CharField("modalidade / subtítulo", max_length=100, default="Vôlei de Praia")
    phone = models.CharField("telefone de contato", max_length=30, blank=True, default="(88) 99267-1163")
    whatsapp = models.CharField("WhatsApp com DDI e DDD", max_length=15, default="5588992671163", validators=[RegexValidator(r"^[1-9][0-9]{9,14}$", "Use somente números, com DDI e DDD.")])
    instagram = models.CharField("Instagram (sem @)", max_length=30, blank=True, default="teamfarias_", validators=[RegexValidator(r"^[A-Za-z0-9._]+$", "Informe o usuário sem @ ou URL.")])
    email = models.EmailField("e-mail de contato", blank=True)
    city = models.CharField("cidade", max_length=80, default="Tianguá")
    state = models.CharField("UF", max_length=2, default="CE", validators=[RegexValidator(r"^[A-Z]{2}$", "Informe a sigla em maiúsculas.")])
    address = models.CharField("endereço confirmado", max_length=250, blank=True)
    pix = models.CharField("chave Pix (somente área do aluno)", max_length=150, blank=True)
    logo_url = models.URLField("URL da logo", blank=True, validators=[URLValidator(schemes=["https"])], help_text="Imagem HTTPS. Deixe vazio para usar o emblema atual.")
    accent_color = models.CharField("cor de destaque", max_length=7, default="#A45CFF", validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use uma cor hexadecimal, como #A45CFF.")])
    hero_title = models.CharField("título principal", max_length=140, default="A escolinha organizada.")
    hero_highlight = models.CharField("destaque do título", max_length=140, default="O time mais conectado.")
    hero_description = models.TextField("texto principal", default="Vôlei de praia em Tianguá, Ceará. Fale com o Team Farias pelo WhatsApp para consultar o plano, os horários e as matrículas.")
    meta_description = models.CharField("descrição para buscas", max_length=300, default="Team Farias — vôlei de praia em Tianguá, Ceará. Consulte planos, valores e informações pelo WhatsApp.")
    about_title = models.CharField("título sobre a escolinha", max_length=140, default="Team Farias na areia.")
    about_text = models.TextField("sobre a escolinha", default="Conheça o Team Farias e converse com a equipe para saber mais sobre os treinos em Tianguá.")
    footer_text = models.TextField("texto do rodapé", default="Team Farias — Vôlei de Praia em Tianguá, Ceará.")
    cta_title = models.CharField("título do convite", max_length=140, default="Vem para o Team Farias.")
    cta_text = models.TextField("texto do convite", default="Consulte valores, horários e disponibilidade pelo WhatsApp. A equipe orienta sua matrícula e libera o acesso à área do aluno.")
    whatsapp_label = models.CharField("texto do botão de contato", max_length=60, default="Falar com a equipe")
    plan_title = models.CharField("título da consulta de planos", max_length=80, default="Seu plano de treino")
    plan_description = models.TextField("descrição pública do plano", default="Consulte valores, horários e condições diretamente com a equipe pelo WhatsApp.")
    show_about = models.BooleanField("mostrar sobre a escolinha", default=True)
    show_system = models.BooleanField("mostrar recursos do sistema", default=True)
    show_steps = models.BooleanField("mostrar como funciona", default=True)
    show_groups = models.BooleanField("mostrar turmas cadastradas", default=True)
    show_news = models.BooleanField("mostrar notícias", default=True)
    show_stats = models.BooleanField("mostrar contadores reais", default=False)
    show_next_session = models.BooleanField("mostrar próximo treino", default=False)
    auto_install_prompt = models.BooleanField("convidar a instalar automaticamente", default=False)
    minimum_age = models.PositiveSmallIntegerField("idade mínima para matrícula", default=0, validators=[MaxValueValidator(99)], help_text="0 para não exigir idade mínima. Responsável obrigatório para menores de 18 anos.")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "configuração do site"
        verbose_name_plural = "configurações do site"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="site_configuration_singleton")]

    def __str__(self):
        return "Configurações do Team Farias"

    @classmethod
    def current(cls):
        return cls.objects.filter(pk=1).first() or cls()

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
