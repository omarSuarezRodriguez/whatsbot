class BusinessProfile {
  BusinessProfile({
    required this.id,
    required this.name,
    required this.twilioWhatsappFrom,
    required this.adminWhatsappNumber,
    required this.sheetsEnabled,
  });

  final String id;
  final String name;
  final String twilioWhatsappFrom;
  final String adminWhatsappNumber;
  final bool sheetsEnabled;

  factory BusinessProfile.fromJson(Map<String, dynamic> json) {
    return BusinessProfile(
      id: json['id'] as String,
      name: json['name'] as String,
      twilioWhatsappFrom: json['twilio_whatsapp_from'] as String? ?? '',
      adminWhatsappNumber: json['admin_whatsapp_number'] as String? ?? '',
      sheetsEnabled: json['sheets_enabled'] as bool? ?? false,
    );
  }
}

class LoginResult {
  LoginResult({
    required this.accessToken,
    required this.businessId,
    required this.businessName,
  });

  final String accessToken;
  final String businessId;
  final String businessName;

  factory LoginResult.fromJson(Map<String, dynamic> json) {
    return LoginResult(
      accessToken: json['access_token'] as String,
      businessId: json['business_id'] as String,
      businessName: json['business_name'] as String? ?? '',
    );
  }
}
