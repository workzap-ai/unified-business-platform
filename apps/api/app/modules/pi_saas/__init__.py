"""Standalone Pi WhatsApp SaaS: business accounts, onboarding, plans and entitlement,
WhatsApp provider connections, platform-operator management and usage metering.

Each Pi business is its own tenant (never merged by owner or phone number). The tenant,
environments, PI installation and roles are provisioned behind the scenes; customers never
see Owner OS concepts. The conversation runtime, tools, CRM, orders and billing are the
shared core services in ``app.modules.pi`` and the business modules.
"""
