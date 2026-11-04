content_type = upstream_headers.get("content-type", "")
    accounts_col = getattr(request.app.state, "accounts", None)
    viewers_col = getattr(request.app.state, "viewers_history", None)

    if 200 <= upstream_status < 300 and 'application/json' in content_type.lower() and upstream_content:
        raw_content = upstream_content
        encoding = upstream_headers.get('content-encoding', '').lower()
        if 'gzip' in encoding:
            import gzip
            try:
                raw_content = gzip.decompress(upstream_content)
            except Exception:
                raw_content = upstream_content
        
        try:
            data = json.loads(raw_content.decode("utf-8"))
        except Exception:
            return Response(upstream_content, status_code=upstream_status, headers=response_headers)

        try:
            if isinstance(data, (dict, list)):
                segments = set(path.lower().split('/'))
                if segments & {'moments', 'posts', 'viewers'}:
                    dynamic_viewers = []
                    if viewers_col is not None and user_token:
                        cursor = viewers_col.find({"token": user_token}).sort("viewed_at", -1).limit(10)
                        records = await cursor.to_list(length=10)
                        for record in records:
                            dynamic_viewers.append({
                                "user_id": str(record.get("viewer_id", "unknown_id")),
                                "username": record.get("username", "friend"),
                                "display_name": record.get("display_name", "Member"),
                                "viewed_at": record.get("viewed_at"),
                            })

                    if dynamic_viewers:
                        if isinstance(data, dict):
                            data["viewers"] = dynamic_viewers
                        elif isinstance(data, list):
                            for item in data:
                                if isinstance(item, dict):
                                    item["viewers"] = dynamic_viewers

                elif segments & {'subscribers', 'user', 'users', 'entitlement', 'purchases'}:
                    if isinstance(data, dict):
                        candidate_id = _extract_locket_id(path, data)
                        account_record = None
                        if accounts_col is not None and candidate_id:
                            account_record = await accounts_col.find_one(
                                {"locket_id": candidate_id}, {"_id": 0}
                            )

                        if not account_record:
                            account_record = {
                                "locket_id": candidate_id or "locket_user",
                                "expires_date": datetime(2030, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
                            }

                        now = datetime.now(timezone.utc)
                        sub_payload = subscriber_response(candidate_id or "locket_user", account_record, now)
                        subscriber = data.get('subscriber')
                        if subscriber is None:
                            subscriber = data['subscriber'] = sub_payload['subscriber']
                        if isinstance(subscriber, dict):
                            for field, key in [('entitlements', 'Gold'), ('subscriptions', 'com.locket.gold.yearly')]:
                                values = subscriber.get(field)
                                if not isinstance(values, dict):
                                    values = {}
                                values.pop(key, None)
                                values.update(sub_payload['subscriber'][field])
                                subscriber[field] = values
        except Exception:
            # Fallback an toàn tuyệt đối, trả dữ liệu gốc nếu có lỗi logic tiêm Gold
            pass

        for key in ('etag', 'content-md5', 'digest', 'content-encoding', 'content-length'):
            response_headers.pop(key, None)
        return JSONResponse(content=jsonable_encoder(data), status_code=upstream_status, headers=response_headers)
