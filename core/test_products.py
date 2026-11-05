import io
import shutil
import tempfile
from urllib.parse import parse_qs, urlparse

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from billing.models import Invoice, Payment
from .models import Product
from .product_forms import ProductForm, ProductOrderForm
from .testing import make_admin, make_professor, make_student, make_invoice


def photo(fmt="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", (64, 64), "purple").save(stream, fmt)
    return SimpleUploadedFile("foto." + fmt.lower(), stream.getvalue(), content_type="image/" + fmt.lower())


class ProductWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = make_admin()
        cls.professor = make_professor()
        cls.student = make_student()
        cls.product = Product.objects.create(name="Camisa de teste", category="Camisas", description="Material e personalização", image="products/test.webp", is_active=True, sizes="P, M, G", colors="Preta, Roxa", customize_name=True, customize_number=True)
        cls.draft = Product.objects.create(name="Rascunho reservado")

    def setUp(self):
        self.media = tempfile.mkdtemp(prefix="tf-product-test-")
        setting = override_settings(MEDIA_ROOT=self.media)
        setting.enable()
        self.addCleanup(setting.disable)
        self.addCleanup(shutil.rmtree, self.media)

    def order_data(self, **changes):
        return {"customer_name":"Maria Silva", "size":"M", "color":"Roxa", "print_name":"MARIA", "print_number":"07", "quantity":"2", "notes":"Consultar retirada", **changes}

    def test_public_and_internal_catalog_routes(self):
        response=self.client.get(reverse("core:products"))
        self.assertContains(response,self.product.name)
        self.assertNotContains(response,self.draft.name)
        self.assertEqual(self.client.get(reverse("dashboard:shop")).status_code,302)
        for user in [self.admin,self.professor,self.student.user]:
            self.client.force_login(user)
            for route in [reverse("dashboard:shop"),reverse("dashboard:shop_product",args=[self.product.pk])]:
                response=self.client.get(route,HTTP_HX_BOOSTED="true")
                self.assertEqual(response.status_code,200)
                self.assertContains(response,'class="app-body"')
                self.assertIn("no-store",response['Cache-Control'])

    def test_drafts_cannot_be_opened_or_ordered_even_by_id(self):
        for method in [self.client.get,self.client.post]:
            self.assertEqual(method(reverse("core:product",args=[self.draft.pk])).status_code,404)

    def test_order_review_builds_exact_encoded_whatsapp_message(self):
        response=self.client.post(self.product.get_absolute_url(),self.order_data(),HTTP_HX_BOOSTED="true")
        self.assertEqual(response.status_code,200)
        self.assertNotIn('Location',response)
        url=urlparse(response.context['whatsapp_url'])
        self.assertEqual(url.netloc,'wa.me')
        self.assertEqual(url.path,'/5588992671163')
        message=parse_qs(url.query)['text'][0]
        for text in ['Nome na estampa: MARIA','Número na estampa: 07','Tamanho: M','Cor: Roxa','Quantidade: 2']:
            self.assertIn(text,message)
        self.assertContains(response,'Nada foi enviado ainda')
        self.assertIn('no-store',response['Cache-Control'])

    def test_edit_preserves_data_without_stale_whatsapp_link(self):
        response=self.client.post(self.product.get_absolute_url(),self.order_data(action='edit'))
        self.assertNotIn('whatsapp_url',response.context)
        self.assertContains(response,'value="MARIA"')
        self.assertContains(response,'Revisar pedido')

    def test_order_rejects_invalid_or_missing_options(self):
        for changes in [{'size':'XXL'},{'color':'Azul'},{'quantity':'0'},{'quantity':'51'},{'quantity':'1.5'},{'print_number':'100'},{'print_number':'-1'},{'print_name':''},{'customer_name':''}]:
            with self.subTest(changes=changes):
                response=self.client.post(self.product.get_absolute_url(),self.order_data(**changes))
                self.assertNotIn('whatsapp_url',response.context)
                self.assertTrue(response.context['form'].errors)

    def test_pausing_orders_or_changing_sizes_invalidates_old_form(self):
        self.product.order_enabled=False;self.product.save()
        response=self.client.post(self.product.get_absolute_url(),self.order_data())
        self.assertNotIn('whatsapp_url',response.context)
        self.assertContains(response,'Pedidos pausados')
        self.product.order_enabled=True;self.product.sizes='G';self.product.save()
        response=self.client.post(self.product.get_absolute_url(),self.order_data())
        self.assertTrue(response.context['form'].errors['size'])

    def test_simple_products_do_not_request_or_accept_customization(self):
        product=Product.objects.create(name='Acessório',is_active=True,price='20.00')
        product.refresh_from_db()
        form=ProductOrderForm(self.order_data(),product=product)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertNotIn('Nome na estampa',form.message())
        self.assertNotIn('Tamanho',form.message())
        self.assertIn('R$ 20,00',form.message())

    def test_html_is_escaped_and_message_characters_preserved(self):
        value='<script>alert(1)</script> & + 🎽'
        response=self.client.post(self.product.get_absolute_url(),self.order_data(notes=value))
        self.assertNotContains(response,'<script>alert(1)</script>')
        self.assertIn(value,parse_qs(urlparse(response.context['whatsapp_url']).query)['text'][0])

    def test_only_admin_can_manage_products(self):
        for user in [self.professor,self.student.user]:
            self.client.force_login(user)
            for path in [reverse('dashboard:products'),reverse('dashboard:product_create'),reverse('dashboard:product_edit',args=[self.product.pk])]:
                self.assertEqual(self.client.get(path).status_code,403)
                self.assertEqual(self.client.post(path,{'name':'Inválido'}).status_code,403)

    def test_admin_creates_optimized_photo_and_edits_product(self):
        self.client.force_login(self.admin)
        data={'name':'Camisa publicada','category':'Camisas','description':'Treino','sizes':'P, M, M, G','colors':'Roxa','position':0,'is_active':'on','order_enabled':'on','customize_name':'on','image':photo()}
        response=self.client.post(reverse('dashboard:product_create'),data)
        self.assertEqual(response.status_code,302)
        item=Product.objects.get(name='Camisa publicada')
        self.assertEqual(item.sizes,'P, M, G')
        self.assertTrue(item.image.name.endswith('.webp'))
        with Image.open(item.image.path) as img:
            self.assertEqual(img.format,'WEBP');self.assertFalse(img.getexif())
        data.pop('image');data.pop('is_active');data['price']='79.90'
        response=self.client.post(reverse('dashboard:product_edit',args=[item.pk]),data)
        self.assertEqual(response.status_code,302)
        item.refresh_from_db();self.assertFalse(item.is_active)
        self.assertEqual(str(item.price),'79.90')

    def test_publication_needs_photo_and_price_cannot_be_negative(self):
        form=ProductForm({'name':'Camisa','category':'Camisas','position':0,'is_active':'on','price':'-2'})
        self.assertFalse(form.is_valid());self.assertIn('image',form.errors);self.assertIn('price',form.errors)

    def test_invalid_image_and_oversize_upload_rejected(self):
        for upload in [SimpleUploadedFile('x.svg',b'<svg><script>alert(1)</script></svg>',content_type='image/svg+xml'),SimpleUploadedFile('x.jpg',b'not an image',content_type='image/jpeg')]:
            form=ProductForm({'name':'Imagem','category':'Teste','position':0},{'image':upload})
            self.assertFalse(form.is_valid());self.assertIn('image',form.errors)
        upload=photo();upload.size=9*1024*1024
        form=ProductForm({'name':'Imagem','category':'Teste','position':0},{'image':upload})
        self.assertFalse(form.is_valid());self.assertIn('image',form.errors)

    def test_csrf_required_for_orders_and_admin_mutations(self):
        client=Client(enforce_csrf_checks=True)
        self.assertEqual(client.post(self.product.get_absolute_url(),self.order_data()).status_code,403)
        client.force_login(self.admin)
        self.assertEqual(client.post(reverse('dashboard:product_create'),{'name':'Teste'}).status_code,403)

    def test_reopening_invoice_then_paying_again_has_one_current_payment(self):
        invoice=make_invoice(self.student)
        invoice.mark_paid(user=self.admin)
        self.client.force_login(self.admin)
        page=self.client.get(reverse('dashboard:billing'))
        self.assertContains(page,'id="action-confirm"')
        response=self.client.post(reverse('dashboard:billing'),{'action':'reopen','invoice':invoice.pk},HTTP_HX_BOOSTED='true',follow=True)
        self.assertEqual(response.status_code,200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status,Invoice.Status.ABERTA)
        self.assertIsNone(invoice.paid_at)
        self.assertFalse(Payment.objects.filter(invoice=invoice).exists())
        self.assertContains(response,'Mensalidade reaberta')
        invoice.mark_paid(user=self.admin);invoice.mark_paid(user=self.admin)
        self.assertEqual(Payment.objects.filter(invoice=invoice).count(),1)

    def test_student_and_professor_cannot_reopen_invoice(self):
        invoice=make_invoice(self.student);invoice.mark_paid(user=self.admin)
        for user in [self.student.user,self.professor]:
            self.client.force_login(user)
            self.assertEqual(self.client.post(reverse('dashboard:billing'),{'action':'reopen','invoice':invoice.pk}).status_code,403)
        invoice.refresh_from_db();self.assertEqual(invoice.status,Invoice.Status.PAGA)
