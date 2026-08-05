"""
URL configuration for crm project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts.views import website_homepage, website_about, website_services, lead_api_create, lead_api_docs

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', website_homepage, name='website_homepage'),
    path('about/', website_about, name='website_about'),
    path('services/', website_services, name='website_services'),
    path('api/leads/create/', lead_api_create, name='lead_api_create'),
    path('api/leads/docs/', lead_api_docs, name='lead_api_docs'),
    path('crm/', include('accounts.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
