from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import owner_views
from . import landlord_views
from . import auth_views as portal_auth_views
from . import blog_views

urlpatterns = [
    path("", views.home, name="home"),
    path("rental-ledger-pro/", views.rental_ledger_pro_home, name="rental_ledger_pro_home"),
    path("rental-ledger-pro/contact/", views.rental_ledger_contact, name="rental_ledger_contact"),
    path("rental-ledger-pro/demo/", views.rental_ledger_demo, name="rental_ledger_demo"),
    path("rental-ledger-pro/demo/reports/<slug:report_slug>/", views.rental_ledger_demo_report, name="rental_ledger_demo_report"),
    path("rental-ledger-pro/<slug:page_slug>/", views.rental_ledger_product_page, name="rental_ledger_product_page"),
    path("demo/", views.demo_entry, name="demo_entry"),
    path("demo/status/", views.demo_status, name="demo_status"),
    path("properties/", views.properties_list, name="properties_list"),
    path("creed/", views.creed, name="creed"),
    path("who-we-serve/", views.who_we_serve, name="who_we_serve"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("terms/", views.terms_of_service, name="terms_of_service"),
    path("property-owner-intake/", views.property_owner_intake, name="property_owner_intake"),
    path("property-owner-intake/success/", views.property_owner_intake_success, name="property_owner_intake_success"),

    path("apply/", views.apply, name="apply"),
    path("apply/success/", views.apply_success, name="apply_success"),
    path("enter-invite-code/", views.enter_invite_code, name="enter_invite_code"),
    path("request-invite-code/", views.request_invite_code, name="request_invite_code"),

    path("signup/", views.signup, name="signup"),
    path("login/", portal_auth_views.role_login, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("password-reset/", auth_views.PasswordResetView.as_view(
        template_name="password_reset.html",
        email_template_name="password_reset_email.html",
        subject_template_name="password_reset_subject.txt",
        success_url="/password-reset/done/"
    ), name="password_reset"),

    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(
        template_name="password_reset_done.html"
    ), name="password_reset_done"),

    path("password-reset-confirm/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="password_reset_confirm.html",
        success_url="/password-reset/complete/"
    ), name="password_reset_confirm"),

    path("password-reset/complete/", auth_views.PasswordResetCompleteView.as_view(
        template_name="password_reset_complete.html"
    ), name="password_reset_complete"),

    path("tenant-dashboard/", views.tenant_dashboard, name="tenant_dashboard"),
    path("tenant-dashboard/balance/", views.resident_balance_detail, name="resident_balance_detail"),
    path("tenant-dashboard/payment-history/", views.resident_payment_history, name="resident_payment_history"),
    path("tenant-dashboard/requests/", views.resident_requests, name="resident_requests"),
    path("tenant-dashboard/profile-photo/", views.update_resident_profile_photo, name="update_resident_profile_photo"),
    path("tenant-dashboard/utility-setup/<int:setup_id>/open/", views.resident_utility_setup_open, name="resident_utility_setup_open"),
    path("landlord-dashboard/", views.landlord_dashboard, name="landlord_dashboard"),
    path("landlord-dashboard/attention/", views.landlord_attention, name="landlord_attention"),
    path("landlord-dashboard/residents/", views.landlord_resident_files, name="landlord_resident_files"),
    path("landlord-dashboard/residents/send-app-codes/", views.bulk_send_resident_app_setup_codes, name="bulk_send_resident_app_setup_codes"),
    path("landlord-dashboard/residents/upload-packet/", views.tenant_file_packet_upload, name="tenant_file_packet_upload"),
    path("landlord-dashboard/residents/packets/<int:document_id>/", views.tenant_file_packet_review, name="tenant_file_packet_review"),
    path("landlord-dashboard/residents/<int:application_id>/send-app-code/", views.send_resident_app_setup_code, name="send_resident_app_setup_code"),
    path("listings/", views.listing_center, name="listing_center"),
    path("listings/create/", views.rental_listing_create, name="rental_listing_create"),
    path("listings/<int:listing_id>/", views.rental_listing_detail, name="rental_listing_detail"),
    path("listings/<int:listing_id>/edit/", views.rental_listing_edit, name="rental_listing_edit"),
    path("listings/<int:listing_id>/channels/", views.rental_listing_update_channels, name="rental_listing_update_channels"),
    path("landlord-dashboard/residents/<int:application_id>/transfer-room/", views.transfer_resident_room, name="transfer_resident_room"),
    path("landlord-dashboard/residents/<int:application_id>/move-out/", views.archive_resident_move_out, name="archive_resident_move_out"),
    path("landlord-dashboard/rent-setup/", views.landlord_rent_setup, name="landlord_rent_setup"),
    path("landlord-dashboard/rent-setup/<int:property_id>/", views.landlord_rent_setup, name="landlord_rent_setup_property"),
    path("landlord-dashboard/current-resident-roster/", views.current_resident_roster_upload, name="current_resident_roster_upload"),
    path("landlord-dashboard/current-resident-intakes/<int:intake_id>/", views.landlord_existing_resident_intake_detail, name="landlord_existing_resident_intake_detail"),
    path("landlord-dashboard/current-resident-intakes/<int:intake_id>/send-invite/", views.landlord_send_existing_resident_invite, name="landlord_send_existing_resident_invite"),
    path("landlord-dashboard/current-resident-intakes/<int:intake_id>/delete/", views.delete_existing_resident_intake, name="delete_existing_resident_intake"),
    path("resident-messages/group/", views.group_resident_message, name="group_resident_message"),
    path("owner-dashboard/", owner_views.property_owner_dashboard, name="property_owner_dashboard"),
    path("owner-dashboard/onboarding/", owner_views.owner_onboarding_wizard, name="owner_onboarding_wizard"),
    path("owner-dashboard/properties/create/", owner_views.owner_property_create, name="owner_property_create"),
    path("owner-dashboard/properties/<int:property_id>/onboarding-documents/", owner_views.owner_property_onboarding_documents, name="owner_property_onboarding_documents"),
    path("owner-dashboard/landlords/invite/", owner_views.owner_landlord_invite, name="owner_landlord_invite"),
    path("owner-dashboard/financial-upload/", owner_views.owner_financial_upload, name="owner_financial_upload"),
    path("superadmin-dashboard/", views.superadmin_dashboard, name="superadmin_dashboard"),
    path("superadmin-dashboard/owners/", views.superadmin_owners, name="superadmin_owners"),
    path("superadmin-dashboard/owner-intakes/", views.superadmin_owner_intakes, name="superadmin_owner_intakes"),
    path("superadmin-dashboard/owner-intakes/<int:intake_id>/", views.superadmin_owner_intake_detail, name="superadmin_owner_intake_detail"),
    path("superadmin-dashboard/owner-intakes/<int:intake_id>/send-invite/", views.superadmin_send_owner_invite, name="superadmin_send_owner_invite"),
    path("superadmin-dashboard/residents/", views.superadmin_residents, name="superadmin_residents"),
    path("superadmin-dashboard/company-mailbox/", views.company_mailbox, name="company_mailbox"),
    path("superadmin-dashboard/company-mailbox/connect/", views.company_mailbox_connect, name="company_mailbox_connect"),
    path("superadmin-dashboard/company-mailbox/callback/", views.company_mailbox_callback, name="company_mailbox_callback"),
    path("superadmin-dashboard/company-mailbox/compose/", views.company_mailbox_compose, name="company_mailbox_compose"),
    path("superadmin-dashboard/company-mailbox/messages/<path:message_id>/", views.company_mailbox_message, name="company_mailbox_message"),
    path("property-blogs/", blog_views.blog_manager, name="property_blog_manager"),
    path("property-blogs/create/", blog_views.blog_create, name="property_blog_create"),
    path("property-blogs/comments/<int:comment_id>/approve/", blog_views.approve_blog_comment, name="approve_blog_comment"),
    path("property-blogs/comments/<int:comment_id>/delete/", blog_views.delete_blog_comment, name="delete_blog_comment"),
    path("landlord/create-tenant/", landlord_views.create_tenant, name="landlord_create_tenant"),
    path("landlord-message/<int:message_id>/", views.landlord_message_detail, name="landlord_message_detail"),
    path("document/<int:document_id>/reviewed/", views.mark_document_reviewed, name="mark_document_reviewed"),

    path("payment-log/", views.payment_log, name="payment_log"),
    path("record-payment/", views.record_manual_payment, name="record_manual_payment"),
    path("record-payment/property/<int:property_id>/", views.record_manual_payment, name="record_manual_payment_property"),
    path("payment/<int:payment_id>/edit/", views.edit_manual_payment, name="edit_manual_payment"),
    path("payment/<int:payment_id>/receipt/", views.payment_receipt, name="payment_receipt"),
    path("resident-files/<int:application_id>/balances/", views.edit_resident_balances, name="edit_resident_balances"),
    path("rent-roll/", views.rent_roll, name="rent_roll"),
    path("custom-reports/", views.custom_reports, name="custom_reports"),
    path("custom-reports/templates/<int:template_id>/run/", views.run_custom_report_template, name="run_custom_report_template"),
    path("t12-report/", views.t12_report, name="t12_report"),
    path("financial-upload/", views.financial_upload, name="financial_upload"),
    path("financial-upload/<int:upload_id>/parse/", views.parse_financial_upload, name="parse_financial_upload"),
    path("accounting/receipts/", views.accounting_receipts, name="accounting_receipts"),
    path("accounting/receipts/<int:receipt_id>/splits/add/", views.add_accounting_receipt_split, name="add_accounting_receipt_split"),
    path("accounting/receipt-splits/<int:split_id>/delete/", views.delete_accounting_receipt_split, name="delete_accounting_receipt_split"),
    path("accounting/receipts/<int:receipt_id>/approve/", views.approve_accounting_receipt, name="approve_accounting_receipt"),
    path("accounting/receipts/<int:receipt_id>/ocr/", views.process_accounting_receipt_ocr, name="process_accounting_receipt_ocr"),
    path("documents/<int:document_id>/open/", views.open_applicant_document, name="open_applicant_document"),

    path("property-financials/<str:property_name>/", views.property_financials, name="property_financials"),

    path("export/payment-log/", views.export_payment_log_csv, name="export_payment_log_csv"),
    path("export/rent-roll/", views.export_rent_roll_csv, name="export_rent_roll_csv"),
    path("export/t12/", views.export_t12_csv, name="export_t12_csv"),

    path("property/<int:pk>/", views.property_detail, name="property_detail"),
    path("rental-listing/<int:listing_id>/", views.public_rental_listing, name="public_rental_listing"),
    path("property/<int:pk>/existing-resident-profile/", views.existing_resident_intake, name="existing_resident_intake"),
    path("property/<int:pk>/existing-resident-profile/success/", views.existing_resident_intake_success, name="existing_resident_intake_success"),
    path("journal/<int:pk>/", views.blog_detail, name="blog_detail"),
    path("blog/<int:post_id>/comment/", views.add_blog_comment, name="add_blog_comment"),

    path("application/<int:pk>/view/", views.printable_application, name="application_detail"),
    path("application/<int:pk>/print/", views.printable_application, name="printable_application"),
    path("application/<int:pk>/screening/", views.application_screening_review, name="application_screening_review"),
    path("application/<int:pk>/adverse-action/", views.create_adverse_action_notice, name="create_adverse_action_notice"),
    path("adverse-action/<int:notice_id>/", views.adverse_action_notice_detail, name="adverse_action_notice_detail"),

    path("lease/sign/", views.lease_sign, name="lease_sign"),
    path("lease/submit/", views.submit_lease_signature, name="submit_lease_signature"),
    path("onboarding/document/<int:document_id>/", views.onboarding_document, name="onboarding_document"),
    path("onboarding/document/<int:document_id>/submit/", views.submit_onboarding_document, name="submit_onboarding_document"),

    path("pay/<int:application_id>/", views.create_checkout_session, name="pay_rent"),
    path("pay/<int:application_id>/<str:payment_type>/", views.create_checkout_session, name="pay_by_type"),

    path("payment-success/", views.payment_success, name="payment_success"),
    path("stripe/webhook/", views.stripe_webhook, name="stripe_webhook"),
    path("sms/twilio/webhook/", views.twilio_sms_webhook, name="twilio_sms_webhook"),

    path("resident-message/submit/", views.submit_resident_message, name="submit_resident_message"),
    path("resident-document/upload/", views.upload_resident_document, name="upload_resident_document"),
]
