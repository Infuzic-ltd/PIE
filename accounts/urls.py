from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('', views.login_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('agents/performance/', views.agent_performance_list, name='agent_performance'),
    path('agents/performance/set-target/', views.set_agent_target, name='set_agent_target'),

    # Properties
    path('properties/', views.property_list, name='property_list'),
    path('properties/create/', views.property_create, name='property_create'),
    path('properties/<int:pk>/', views.property_view, name='property_view'),
    path('properties/<int:pk>/edit/', views.property_update, name='property_update'),
    path('properties/<int:pk>/delete/', views.property_delete, name='property_delete'),
    path('properties/<int:pk>/set-status/', views.property_set_status, name='property_set_status'),
    path('properties/image/<int:pk>/delete/', views.property_image_delete, name='property_image_delete'),
    path('properties/<int:pk>/document/', views.property_add_document, name='property_add_document'),
    path('properties/document/<int:pk>/delete/', views.property_document_delete, name='property_document_delete'),

    # Property Submissions (website listing/evaluation requests)
    path('property-submissions/', views.property_submission_list, name='property_submission_list'),
    path('property-submissions/<int:pk>/', views.property_submission_detail, name='property_submission_detail'),
    path('property-submissions/<int:pk>/update/', views.property_submission_update, name='property_submission_update'),
    path('property-submissions/<int:pk>/convert/', views.property_submission_convert, name='property_submission_convert'),

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

    # Site Settings (admin only)
    path('settings/', views.site_settings_view, name='site_settings'),

    # Blocks (admin only)
    path('blocks/', views.block_list, name='block_list'),
    path('blocks/add-ajax/', views.block_create_ajax, name='block_create_ajax'),
    path('blocks/<int:pk>/delete/', views.block_delete, name='block_delete'),
    path('blocks/<int:pk>/documents/add/', views.block_required_document_add, name='block_required_document_add'),
    path('blocks/documents/<int:pk>/delete/', views.block_required_document_delete, name='block_required_document_delete'),

    # Leads
    path('leads/', views.lead_list, name='lead_list'),
    path('leads/add/', views.lead_create, name='lead_create'),
    path('leads/check-phone/', views.lead_check_phone, name='lead_check_phone'),
    path('leads/<int:pk>/', views.lead_detail, name='lead_detail'),
    path('leads/<int:pk>/edit/', views.lead_update, name='lead_update'),
    path('leads/<int:pk>/delete/', views.lead_delete, name='lead_delete'),
    path('leads/<int:pk>/note/', views.lead_add_note, name='lead_add_note'),
    path('leads/<int:pk>/document/', views.lead_add_document, name='lead_add_document'),
    path('leads/<int:pk>/status/', views.lead_status_update, name='lead_status_update'),
    path('leads/<int:pk>/share-properties/', views.lead_share_properties, name='lead_share_properties'),
    path('leads/<int:pk>/follow-up/', views.lead_auto_follow_up, name='lead_auto_follow_up'),
    path('leads/<int:pk>/schedule-visit/', views.lead_schedule_visit, name='lead_schedule_visit'),
    path('leads/<int:pk>/financials/set/', views.lead_set_deal_financials, name='lead_set_deal_financials'),
    path('leads/<int:pk>/payment/add/', views.lead_add_payment, name='lead_add_payment'),
    path('leads/<int:pk>/payment/<int:payment_pk>/slip/', views.lead_print_payment_slip, name='lead_print_payment_slip'),
    path('leads/<int:pk>/commission-invoice/', views.lead_print_commission_invoice, name='lead_print_commission_invoice'),
    path('leads/<int:pk>/possession-complete/', views.lead_mark_possession_complete, name='lead_mark_possession_complete'),
    path('leads/<int:pk>/invoice/', views.lead_print_invoice, name='lead_print_invoice'),
    path('leads/<int:pk>/slip/<int:doc_pk>/', views.lead_print_slip, name='lead_print_slip'),
    path('leads/<int:pk>/collaborator/add/', views.lead_add_collaborator, name='lead_add_collaborator'),
    path('leads/<int:pk>/collaborator/<int:user_pk>/remove/', views.lead_remove_collaborator, name='lead_remove_collaborator'),

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

    # Notifications
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/<int:pk>/open/', views.notification_open, name='notification_open'),
    path('notifications/mark-all-read/', views.notifications_mark_all_read, name='notifications_mark_all_read'),
    path('notifications/feed/', views.notifications_feed, name='notifications_feed'),
]
