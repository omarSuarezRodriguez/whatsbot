class PendingOrder {
  PendingOrder({
    required this.id,
    required this.businessId,
    required this.orderId,
    required this.waId,
    required this.items,
    required this.total,
    required this.status,
    required this.customerName,
    required this.address,
    required this.deliveryType,
    required this.createdAt,
  });

  final int id;
  final String businessId;
  final String orderId;
  final String waId;
  final List<Map<String, dynamic>> items;
  final double total;
  final String status;
  final String customerName;
  final String address;
  final String deliveryType;
  final DateTime createdAt;

  factory PendingOrder.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return PendingOrder(
      id: json['id'] as int,
      businessId: json['business_id'] as String,
      orderId: json['order_id'] as String,
      waId: json['wa_id'] as String,
      items: rawItems is List
          ? rawItems.map((e) => Map<String, dynamic>.from(e as Map)).toList()
          : [],
      total: (json['total'] as num?)?.toDouble() ?? 0,
      status: json['status'] as String? ?? 'pending',
      customerName: json['customer_name'] as String? ?? '',
      address: json['address'] as String? ?? '',
      deliveryType: json['delivery_type'] as String? ?? '',
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}
