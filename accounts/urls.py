from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.login_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),

    # Properties
    path('properties/', views.property_list, name='property_list'),
    path('properties/create/', views.property_create, name='property_create'),
    path('properties/<int:pk>/', views.property_view, name='property_view'),
    path('properties/<int:pk>/edit/', views.property_update, name='property_update'),
    path('properties/<int:pk>/delete/', views.property_delete, name='property_delete'),
    path('properties/<int:pk>/set-status/', views.property_set_status, name='property_set_status'),
    path('properties/image/<int:pk>/delete/', views.property_image_delete, name='property_image_delete'),

    # Team management (admin only)
    path('team/', views.team_list, name='team_list'),
    path('team/add/', views.team_member_create, name='team_member_create'),
    path('team/<int:pk>/edit/', views.team_member_update, name='team_member_update'),
    path('team/<int:pk>/delete/', views.team_member_delete, name='team_member_delete'),

    # Role management (admin only)
    path('roles/', views.role_list, name='role_list'),
    path('roles/create/', views.role_create, name='role_create'),
    path('roles/<int:pk>/edit/', views.role_update, name='role_update'),
    path('roles/<int:pk>/delete/', views.role_delete, name='role_delete'),

    # Blocks (admin only)
    path('blocks/', views.block_list, name='block_list'),
    path('blocks/add-ajax/', views.block_create_ajax, name='block_create_ajax'),
    path('blocks/<int:pk>/delete/', views.block_delete, name='block_delete'),

    # Leads
    path('leads/', views.lead_list, name='lead_list'),
    path('leads/add/', views.lead_create, name='lead_create'),
    path('leads/<int:pk>/', views.lead_detail, name='lead_detail'),
    path('leads/<int:pk>/edit/', views.lead_update, name='lead_update'),
    path('leads/<int:pk>/delete/', views.lead_delete, name='lead_delete'),
    path('leads/<int:pk>/note/', views.lead_add_note, name='lead_add_note'),
    path('leads/<int:pk>/document/', views.lead_add_document, name='lead_add_document'),
    path('leads/<int:pk>/status/', views.lead_status_update, name='lead_status_update'),
    path('leads/<int:pk>/whatsapp/', views.lead_whatsapp_send, name='lead_whatsapp_send'),
    path('leads/<int:pk>/invoice/', views.lead_print_invoice, name='lead_print_invoice'),
    path('leads/<int:pk>/slip/<int:doc_pk>/', views.lead_print_slip, name='lead_print_slip'),

    # Customers
    path('customers/', views.customer_list, name='customer_list'),
    path('customers/add/', views.customer_create, name='customer_create'),
    path('customers/<int:pk>/', views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', views.customer_update, name='customer_update'),
    path('customers/<int:pk>/delete/', views.customer_delete, name='customer_delete'),

    # Web Push
    path('sw.js', views.service_worker, name='service_worker'),
    path('push/subscribe/', views.push_subscribe, name='push_subscribe'),
    path('push/unsubscribe/', views.push_unsubscribe, name='push_unsubscribe'),
    path('push/test/', views.push_test, name='push_test'),
]
